from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from astrbot.api import logger

from .config import StorageConfig
from .document import DocumentProcessor
from .interfaces import LocalPaperRepository, ObjectStore
from .models import FulltextLocationRecord, PaperRecordDraft


@dataclass(frozen=True)
class PaperImportRequest:
    record: PaperRecordDraft
    source_query: str | None = None
    decision: str = "search_selected"
    enqueue_parse: bool = True
    process_document: bool = True
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
    parser_run_id: str | None = None
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
        self.storage_cfg = storage_cfg or StorageConfig()
        self.document_processor = document_processor

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
        parser_run_id: str | None = None
        source_path = verified.local_path if verified and verified.local_path else None
        source_removed = False
        message = ""

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
            if request.enqueue_parse:
                job_id = await self.repository.enqueue_job(
                    "storage_parse_pdf",
                    dedupe_key=f"storage_parse_pdf:{object_id}",
                    paper_id=paper_id,
                    object_id=object_id,
                    payload={"source_query": request.source_query},
                )
                if request.process_document:
                    try:
                        parser_run_id = await self._process_imported_pdf(
                            paper_id=paper_id,
                            object_id=object_id,
                            object_path=Path(object_path),
                            parse_job_id=job_id,
                            source_query=request.source_query,
                        )
                        message = "storage_parse_pdf completed"
                    except Exception as exc:
                        message = f"storage_parse_pdf failed: {exc}"
                        await self.repository.mark_job_failed_final(job_id, message)
                        logger.warning(
                            "[PaperOS][PaperStorageImporter] document processing failed paper=%s object=%s error=%r",
                            paper_id,
                            object_id,
                            exc,
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
            parser_run_id=parser_run_id,
            imported_pdf=object_id is not None,
            metadata_only=object_id is None,
            source_file_path=source_path,
            source_file_removed=source_removed,
            message=message,
        )

    async def _process_imported_pdf(
        self,
        *,
        paper_id: str,
        object_id: str,
        object_path: Path,
        parse_job_id: str,
        source_query: str | None,
    ) -> str:
        processor = self.document_processor or DocumentProcessor(storage_cfg=self.storage_cfg)
        close_processor = self.document_processor is None
        try:
            tei_xml, document, normalized, chunks = await processor.process_pdf(object_path)
        finally:
            if close_processor:
                await processor.aclose()

        raw_object = await self.object_store.put_bytes(
            tei_xml.encode("utf-8"),
            kind="tei_xml",
            suffix=".tei.xml",
            mime_type="application/tei+xml",
        )
        raw_object_id = await self.repository.register_object(raw_object)
        normalized_object = await self.object_store.put_bytes(
            json.dumps(normalized, ensure_ascii=False).encode("utf-8"),
            kind="normalized_document",
            suffix=".json",
            mime_type="application/json",
        )
        normalized_object_id = await self.repository.register_object(normalized_object)
        version_id = await self.repository.current_version_id(paper_id)
        parser_run_id = await self.repository.persist_document_processing_result(
            paper_id=paper_id,
            version_id=version_id,
            object_id=object_id,
            parser_name="grobid",
            parser_version=None,
            raw_output_object_id=raw_object_id,
            normalized_object_id=normalized_object_id,
            document=document,
            chunks=chunks,
            message="processed by configured GROBID service",
        )
        await self.repository.mark_job_done(parse_job_id)
        await self.repository.enqueue_job(
            "rag_embed_chunks",
            dedupe_key=f"rag_embed_chunks:{parser_run_id}",
            paper_id=paper_id,
            version_id=version_id,
            object_id=object_id,
            payload={"parser_run_id": parser_run_id, "source_query": source_query},
        )
        return parser_run_id

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
