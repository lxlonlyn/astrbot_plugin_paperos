from __future__ import annotations

from pathlib import Path

from astrbot.api import logger

from .search.models import FulltextStatus, PaperCandidate
from .storage.interfaces import LocalPaperRepository, ObjectStore
from .storage.models import FulltextLocationRecord, PaperRecordDraft


def paper_candidate_to_record(candidate: PaperCandidate) -> PaperRecordDraft:
    """Convert search DTO to storage DTO at the facade boundary.

    This is intentionally outside storage so storage never imports search.
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


class PaperLibraryFacade:
    """Thin orchestration layer between search and storage.

    Search downloads and verifies temporary PDFs. Storage persists papers and
    moves files into its object store. This facade is the only place where these
    two responsibilities meet.
    """

    def __init__(self, *, repository: LocalPaperRepository, object_store: ObjectStore):
        self.repository = repository
        self.object_store = object_store

    async def import_search_candidate(self, candidate: PaperCandidate, *, source_query: str | None = None) -> str:
        record = paper_candidate_to_record(candidate)
        paper_id = await self.repository.upsert_paper(record, source_query=source_query)

        verified = candidate.best_verified_pdf()
        if verified and verified.local_path:
            stored = await self.object_store.put_file(
                Path(verified.local_path),
                kind="pdf",
                suffix=".pdf",
                mime_type=verified.content_type or "application/pdf",
            )
            object_id = await self.repository.register_object(stored)
            await self.repository.attach_object_to_current_version(paper_id=paper_id, object_id=object_id, role="pdf")
            await self.repository.enqueue_job(
                "parse_pdf",
                dedupe_key=f"parse_pdf:{object_id}",
                paper_id=paper_id,
                object_id=object_id,
                payload={"source_query": source_query},
            )
            logger.debug(
                "[PaperOS][LibraryFacade] imported paper=%s object=%s title=%s",
                paper_id,
                object_id,
                candidate.title,
            )
        else:
            logger.debug("[PaperOS][LibraryFacade] imported metadata_without_pdf paper=%s title=%s", paper_id, candidate.title)
        return paper_id
