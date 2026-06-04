from __future__ import annotations

from dataclasses import dataclass, field

from ..search.models import PaperCandidate, PaperSearchResult
from ..storage.config import StorageConfig
from ..storage.document import DocumentProcessor
from ..storage.importer import PaperImportRequest, PaperImportResult, PaperStorageImporter
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
    object_storage_key: str | None = None
    object_path: str | None = None
    job_id: str | None = None
    parser_run_id: str | None = None
    imported_pdf: bool = False
    metadata_only: bool = True
    temporary_pdf_path: str | None = None
    temporary_pdf_removed: bool = False
    message: str = ""

    @classmethod
    def from_storage_result(cls, result: PaperImportResult) -> "SearchStorageImportResult":
        return cls(
            paper_id=result.paper_id,
            title=result.title,
            source=result.source,
            source_query=result.source_query,
            object_id=result.object_id,
            object_storage_key=result.object_storage_key,
            object_path=result.object_path,
            job_id=result.job_id,
            parser_run_id=result.parser_run_id,
            imported_pdf=result.imported_pdf,
            metadata_only=result.metadata_only,
            temporary_pdf_path=result.source_file_path,
            temporary_pdf_removed=result.source_file_removed,
            message=result.message,
        )


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

    def __init__(
        self,
        *,
        repository: LocalPaperRepository,
        object_store: ObjectStore,
        storage_cfg: StorageConfig | None = None,
        document_processor: DocumentProcessor | None = None,
    ):
        self.repository = repository
        self.object_store = object_store
        self.importer = PaperStorageImporter(
            repository=repository,
            object_store=object_store,
            storage_cfg=storage_cfg,
            document_processor=document_processor,
        )

    async def import_search_result(
        self,
        result: PaperSearchResult,
        *,
        source_query: str | None = None,
        selection: str = "selected",
        enqueue_parse: bool = True,
        process_document: bool = True,
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
                    enqueue_parse=enqueue_parse,
                    process_document=process_document,
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
        enqueue_parse: bool = True,
        process_document: bool = True,
        cleanup_temporary_pdf: bool = False,
    ) -> SearchStorageImportResult:
        record = paper_candidate_to_record(candidate)
        result = await self.importer.import_paper(
            PaperImportRequest(
                record=record,
                source_query=source_query,
                decision=decision,
                enqueue_parse=enqueue_parse,
                process_document=process_document,
                cleanup_source_file=cleanup_temporary_pdf,
            )
        )
        return SearchStorageImportResult.from_storage_result(result)

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
