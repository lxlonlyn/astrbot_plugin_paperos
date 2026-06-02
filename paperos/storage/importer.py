from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from astrbot.api import logger

from .interfaces import LocalPaperRepository, ObjectStore
from .models import FulltextLocationRecord, PaperRecordDraft


@dataclass(frozen=True)
class PaperImportRequest:
    record: PaperRecordDraft
    source_query: str | None = None
    decision: str = "search_selected"
    enqueue_rag: bool = True
    cleanup_source_file: bool = False


@dataclass(frozen=True)
class PaperImportResult:
    paper_id: str
    title: str
    source: str
    source_query: str | None = None
    object_id: str | None = None
    object_storage_key: str | None = None
    object_path: str | None = None
    job_id: str | None = None
    imported_pdf: bool = False
    metadata_only: bool = True
    source_file_path: str | None = None
    source_file_removed: bool = False
    message: str = ""


class PaperStorageImporter:
    """Storage-owned importer for paper metadata and verified local artifacts.

    The importer consumes storage DTOs only. Search DTO conversion stays in the
    workflow layer so this module remains persistence-focused and offline.
    """

    def __init__(self, *, repository: LocalPaperRepository, object_store: ObjectStore):
        self.repository = repository
        self.object_store = object_store

    async def import_paper(self, request: PaperImportRequest) -> PaperImportResult:
        record = request.record
        paper_id = await self.repository.upsert_paper(
            record,
            source_query=request.source_query,
            decision=request.decision,
        )

        verified = best_verified_pdf_location(record)
        object_id: str | None = None
        object_storage_key: str | None = None
        object_path: str | None = None
        job_id: str | None = None
        source_path = verified.local_path if verified and verified.local_path else None
        source_removed = False

        if verified and verified.local_path:
            stored = await self.object_store.put_file(
                Path(verified.local_path),
                kind="pdf",
                suffix=".pdf",
                mime_type=verified.content_type or "application/pdf",
            )
            object_id = await self.repository.register_object(stored)
            object_storage_key = stored.storage_key
            object_path = str(stored.path)
            await self.repository.attach_object_to_current_version(
                paper_id=paper_id,
                object_id=object_id,
                role="pdf",
            )
            await self.repository.attach_object_to_fulltext_location(
                paper_id=paper_id,
                url=verified.url,
                object_id=object_id,
            )
            if request.enqueue_rag:
                job_id = await self.repository.enqueue_job(
                    "rag_index_pdf",
                    dedupe_key=f"rag_index_pdf:{object_id}",
                    paper_id=paper_id,
                    object_id=object_id,
                    payload={"source_query": request.source_query},
                )
            if request.cleanup_source_file:
                source_removed = self._remove_source_file(verified.local_path)

        logger.debug(
            "[PaperOS][PaperStorageImporter] imported paper=%s object=%s job=%s title=%s",
            paper_id,
            object_id,
            job_id,
            record.title,
        )
        return PaperImportResult(
            paper_id=paper_id,
            title=record.title,
            source=record.source,
            source_query=request.source_query,
            object_id=object_id,
            object_storage_key=object_storage_key if object_id else None,
            object_path=object_path if object_id else None,
            job_id=job_id,
            imported_pdf=object_id is not None,
            metadata_only=object_id is None,
            source_file_path=source_path,
            source_file_removed=source_removed,
        )

    def _remove_source_file(self, path: str) -> bool:
        try:
            target = Path(path)
            if target.exists():
                target.unlink()
                return True
        except OSError as exc:
            logger.warning("[PaperOS] failed to remove imported source PDF %s: %r", path, exc)
        return False


def best_verified_pdf_location(record: PaperRecordDraft) -> FulltextLocationRecord | None:
    candidates = [
        loc
        for loc in record.fulltext_locations
        if loc.status == "verified_pdf" and loc.local_path
    ]
    if not candidates:
        return None

    def key(loc: FulltextLocationRecord) -> tuple[float, int, int, int]:
        return (
            loc.confidence or 0.0,
            1 if loc.page_count else 0,
            1 if loc.sha256 else 0,
            int(loc.size_bytes or 0),
        )

    return max(candidates, key=key)
