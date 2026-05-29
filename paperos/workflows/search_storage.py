from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from astrbot.api import logger

from ..search.models import PaperCandidate, PaperSearchResult
from ..storage.interfaces import LocalPaperRepository, ObjectStore
from ..storage.models import FulltextLocationRecord, PaperRecordDraft


def paper_candidate_to_record(candidate: PaperCandidate) -> PaperRecordDraft:
    """Convert search DTO to storage DTO at the workflow boundary.

    Storage intentionally does not import search DTOs. This adapter lives in the
    cross-module workflow layer because it composes search output, storage
    metadata upsert, object archival, and future RAG indexing jobs.
    """

    return PaperRecordDraft(
        title=candidate.title,
        authors=list(candidate.authors),
        year=candidate.year,
        venue=candidate.venue,
        publisher=candidate.publisher,
        abstract=candidate.abstract,
        doi=candidate.doi,
        arxiv_id=candidate.arxiv_id,
        core_id=candidate.core_id,
        openalex_id=candidate.openalex_id,
        semantic_scholar_id=candidate.semantic_scholar_id,
        citation_count=candidate.citation_count,
        source=candidate.source,
        landing_url=candidate.landing_url,
        score=candidate.score,
        score_reason=candidate.score_reason,
        raw=dict(candidate.raw or {}),
        fulltext_locations=[
            FulltextLocationRecord(
                url=loc.url,
                source=loc.source,
                kind=loc.kind,
                status=loc.status.value if hasattr(loc.status, "value") else str(loc.status),
                license=loc.license,
                version=loc.version,
                host_type=loc.host_type,
                confidence=loc.confidence,
                reason=loc.reason,
                local_path=loc.local_path,
                final_url=loc.final_url,
                filename=loc.filename,
                sha256=loc.sha256,
                size_bytes=loc.size_bytes,
                content_type=loc.content_type,
                page_count=loc.page_count,
            )
            for loc in candidate.fulltext_locations
        ],
    )


@dataclass(frozen=True)
class SearchStorageImportResult:
    paper_id: str
    title: str
    source: str
    source_query: str | None = None
    object_id: str | None = None
    job_id: str | None = None
    imported_pdf: bool = False
    metadata_only: bool = True
    temporary_pdf_path: str | None = None
    temporary_pdf_removed: bool = False
    message: str = ""


@dataclass(frozen=True)
class SearchStorageImportSummary:
    results: list[SearchStorageImportResult] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        return len(self.results)

    @property
    def pdf_count(self) -> int:
        return sum(1 for item in self.results if item.imported_pdf)

    @property
    def job_count(self) -> int:
        return sum(1 for item in self.results if item.job_id)


class SearchStorageImportWorkflow:
    """Workflow boundary for persisting search results into storage.

    This is intentionally not part of `search` or `storage`: search should not
    write SQLite/object-store state, and storage should not know about search
    DTOs. RAG remains downstream and is represented here only by queued jobs.
    """

    def __init__(self, *, repository: LocalPaperRepository, object_store: ObjectStore):
        self.repository = repository
        self.object_store = object_store

    async def import_search_result(
        self,
        result: PaperSearchResult,
        *,
        source_query: str | None = None,
        selection: str = "selected",
        enqueue_rag: bool = True,
        cleanup_temporary_pdf: bool = False,
    ) -> SearchStorageImportSummary:
        candidates = self._candidates_to_import(result, selection=selection)
        imports: list[SearchStorageImportResult] = []
        for candidate in candidates:
            imports.append(
                await self.import_search_candidate(
                    candidate,
                    source_query=source_query or (result.plan.raw_query if result.plan else None),
                    decision=f"search_{selection}",
                    enqueue_rag=enqueue_rag,
                    cleanup_temporary_pdf=cleanup_temporary_pdf,
                )
            )
        return SearchStorageImportSummary(imports)

    async def import_search_candidate(
        self,
        candidate: PaperCandidate,
        *,
        source_query: str | None = None,
        decision: str = "search_selected",
        enqueue_rag: bool = True,
        cleanup_temporary_pdf: bool = False,
    ) -> SearchStorageImportResult:
        record = paper_candidate_to_record(candidate)
        paper_id = await self.repository.upsert_paper(
            record,
            source_query=source_query,
            decision=decision,
        )

        verified = candidate.best_verified_pdf()
        object_id: str | None = None
        job_id: str | None = None
        temp_path = verified.local_path if verified and verified.local_path else None
        temp_removed = False

        if verified and verified.local_path:
            stored = await self.object_store.put_file(
                Path(verified.local_path),
                kind="pdf",
                suffix=".pdf",
                mime_type=verified.content_type or "application/pdf",
            )
            object_id = await self.repository.register_object(stored)
            await self.repository.attach_object_to_current_version(
                paper_id=paper_id,
                object_id=object_id,
                role="pdf",
            )
            if enqueue_rag:
                job_id = await self.repository.enqueue_job(
                    "rag_index_pdf",
                    dedupe_key=f"rag_index_pdf:{object_id}",
                    paper_id=paper_id,
                    object_id=object_id,
                    payload={"source_query": source_query},
                )
            if cleanup_temporary_pdf:
                temp_removed = self._remove_temporary_pdf(verified.local_path)

        logger.debug(
            "[PaperOS][SearchStorageImportWorkflow] imported paper=%s object=%s job=%s title=%s",
            paper_id,
            object_id,
            job_id,
            candidate.title,
        )
        return SearchStorageImportResult(
            paper_id=paper_id,
            title=candidate.title,
            source=candidate.source,
            source_query=source_query,
            object_id=object_id,
            job_id=job_id,
            imported_pdf=object_id is not None,
            metadata_only=object_id is None,
            temporary_pdf_path=temp_path,
            temporary_pdf_removed=temp_removed,
        )

    def _candidates_to_import(
        self,
        result: PaperSearchResult,
        *,
        selection: str,
    ) -> list[PaperCandidate]:
        if selection == "selected":
            return list(result.selected or result.candidates)
        if selection == "all_candidates":
            return list(result.candidates)
        raise ValueError(f"unsupported search import selection: {selection!r}")

    def _remove_temporary_pdf(self, path: str) -> bool:
        try:
            target = Path(path)
            if target.exists():
                target.unlink()
                return True
        except OSError as exc:
            logger.warning("[PaperOS] failed to remove temporary search PDF %s: %r", path, exc)
        return False
