from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..search.models import PaperSearchResult, SearchContext
from .search_storage import (
    SearchStorageImportResult,
    SearchStorageImportSummary,
    SearchStorageImportWorkflow,
)


class PaperSearchFacade(Protocol):
    async def search(
        self,
        raw_query: str,
        *,
        event: Any | None = None,
        need_fulltext: bool = True,
        context: SearchContext | None = None,
    ) -> PaperSearchResult: ...


class RagIndexFacade(Protocol):
    async def index_parser_run(self, parser_run_id: str) -> Any: ...


@dataclass(frozen=True)
class RagIndexAttempt:
    parser_run_id: str
    paper_id: str | None = None
    rag_job_id: str | None = None
    ok: bool = False
    vector_count: int = 0
    index_name: str | None = None
    profile: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DiscoveryPipelineResult:
    """User-level discovery pipeline result.

    The first implementation intentionally does not bypass PaperOS jobs. It
    runs the synchronous stages that already exist, then reports queued storage
    document-processing jobs for downstream workers.
    """

    query: str
    search_result: PaperSearchResult
    import_summary: SearchStorageImportSummary | None = None
    auto_import: bool = True
    need_fulltext: bool = True
    storage_parse_job_ids: list[str] = field(default_factory=list)
    rag_job_ids: list[str] = field(default_factory=list)
    rag_index_attempts: list[RagIndexAttempt] = field(default_factory=list)
    import_error: str | None = None

    @property
    def imported_count(self) -> int:
        return self.import_summary.imported_count if self.import_summary else 0

    @property
    def pdf_count(self) -> int:
        return self.import_summary.pdf_count if self.import_summary else 0

    @property
    def rag_index_failed_count(self) -> int:
        return sum(1 for item in self.rag_index_attempts if not item.ok)

    @property
    def rag_indexed_vector_count(self) -> int:
        return sum(item.vector_count for item in self.rag_index_attempts if item.ok)


class PaperDiscoveryWorkflow:
    """User-level workflow for search -> storage -> downstream jobs.

    This workflow is the orchestration layer. It does not belong to search,
    storage, or rag. Search still owns online discovery, storage owns
    persistence/document-processing jobs, and RAG consumes parsed chunks later.
    """

    def __init__(
        self,
        *,
        search_service: PaperSearchFacade,
        search_storage: SearchStorageImportWorkflow | None = None,
        rag_index_service: RagIndexFacade | None = None,
    ):
        self.search_service = search_service
        self.search_storage = search_storage
        self.rag_index_service = rag_index_service

    async def discover_and_index(
        self,
        query: str,
        *,
        event: Any | None = None,
        need_fulltext: bool = True,
        auto_import: bool = True,
        selection: str = "selected",
        process_document: bool = True,
        cleanup_temporary_pdf: bool = True,
        ignore_import_errors: bool = False,
        search_context: SearchContext | None = None,
    ) -> DiscoveryPipelineResult:
        search_result = await self.search_service.search(
            raw_query=query,
            event=event,
            need_fulltext=need_fulltext,
            context=search_context,
        )

        import_summary: SearchStorageImportSummary | None = None
        import_error: str | None = None
        rag_index_attempts: list[RagIndexAttempt] = []
        if auto_import and self.search_storage is not None and search_result.candidates:
            try:
                import_summary = await self.search_storage.import_search_result(
                    search_result,
                    source_query=query,
                    selection=selection,
                    enqueue_parse=True,
                    process_document=process_document,
                    cleanup_temporary_pdf=cleanup_temporary_pdf,
                )
            except Exception as exc:
                if not ignore_import_errors:
                    raise
                import_error = repr(exc)

        if import_summary is not None and self.rag_index_service is not None:
            rag_index_attempts = await self._index_parser_runs(import_summary)

        return DiscoveryPipelineResult(
            query=query,
            search_result=search_result,
            import_summary=import_summary,
            auto_import=auto_import,
            need_fulltext=need_fulltext,
            storage_parse_job_ids=self._job_ids(import_summary),
            rag_job_ids=self._rag_job_ids(import_summary),
            rag_index_attempts=rag_index_attempts,
            import_error=import_error,
        )

    def _job_ids(self, summary: SearchStorageImportSummary | None) -> list[str]:
        if summary is None:
            return []
        return [item.job_id for item in summary.results if item.job_id]

    def _rag_job_ids(self, summary: SearchStorageImportSummary | None) -> list[str]:
        if summary is None:
            return []
        return [item.rag_job_id for item in summary.results if item.rag_job_id]

    async def _index_parser_runs(self, summary: SearchStorageImportSummary) -> list[RagIndexAttempt]:
        service = self.rag_index_service
        if service is None:
            return []

        attempts: list[RagIndexAttempt] = []
        for item in summary.results:
            if not item.parser_run_id:
                continue
            try:
                result = await service.index_parser_run(item.parser_run_id)
                await self._mark_rag_job_done(item)
                attempts.append(
                    RagIndexAttempt(
                        parser_run_id=item.parser_run_id,
                        paper_id=item.paper_id,
                        rag_job_id=item.rag_job_id,
                        ok=True,
                        vector_count=int(getattr(result, "vector_count", 0) or 0),
                        index_name=getattr(result, "index_name", None),
                        profile=getattr(result, "profile", None),
                    )
                )
            except Exception as exc:
                error = str(exc) or repr(exc)
                await self._mark_rag_index_failed(item, error)
                attempts.append(
                    RagIndexAttempt(
                        parser_run_id=item.parser_run_id,
                        paper_id=item.paper_id,
                        rag_job_id=item.rag_job_id,
                        ok=False,
                        error=error,
                    )
                )
        return attempts

    async def _mark_rag_job_done(self, item: SearchStorageImportResult) -> None:
        if self.search_storage is None or not item.rag_job_id:
            return
        await self.search_storage.repository.mark_job_done(item.rag_job_id)

    async def _mark_rag_index_failed(self, item: SearchStorageImportResult, error: str) -> None:
        if self.search_storage is None:
            return
        repository = self.search_storage.repository
        if item.rag_job_id:
            await repository.mark_job_failed_final(item.rag_job_id, error)
        if item.paper_id:
            cfg = getattr(self.rag_index_service, "cfg", None)
            index_name = getattr(cfg, "vector_table_name", "chunk_embeddings")
            await repository.update_index_status(
                paper_id=item.paper_id,
                index_name=index_name,
                status="failed",
                profile=None,
                message=error,
            )
