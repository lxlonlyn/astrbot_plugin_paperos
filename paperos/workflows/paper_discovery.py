from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..search.models import PaperSearchResult
from .search_storage import SearchStorageImportSummary, SearchStorageImportWorkflow


class PaperSearchFacade(Protocol):
    async def search(self, raw_query: str, *, event: Any | None = None, need_fulltext: bool = True) -> PaperSearchResult: ...


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
    import_error: str | None = None

    @property
    def imported_count(self) -> int:
        return self.import_summary.imported_count if self.import_summary else 0

    @property
    def pdf_count(self) -> int:
        return self.import_summary.pdf_count if self.import_summary else 0


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
    ):
        self.search_service = search_service
        self.search_storage = search_storage

    async def discover_and_index(
        self,
        query: str,
        *,
        event: Any | None = None,
        need_fulltext: bool = True,
        auto_import: bool = True,
        selection: str = "selected",
        cleanup_temporary_pdf: bool = True,
        ignore_import_errors: bool = False,
    ) -> DiscoveryPipelineResult:
        search_result = await self.search_service.search(
            raw_query=query,
            event=event,
            need_fulltext=need_fulltext,
        )

        import_summary: SearchStorageImportSummary | None = None
        import_error: str | None = None
        if auto_import and self.search_storage is not None and search_result.candidates:
            try:
                import_summary = await self.search_storage.import_search_result(
                    search_result,
                    source_query=query,
                    selection=selection,
                    enqueue_parse=True,
                    cleanup_temporary_pdf=cleanup_temporary_pdf,
                )
            except Exception as exc:
                if not ignore_import_errors:
                    raise
                import_error = repr(exc)

        return DiscoveryPipelineResult(
            query=query,
            search_result=search_result,
            import_summary=import_summary,
            auto_import=auto_import,
            need_fulltext=need_fulltext,
            storage_parse_job_ids=self._job_ids(import_summary),
            rag_job_ids=[],
            import_error=import_error,
        )

    def _job_ids(self, summary: SearchStorageImportSummary | None) -> list[str]:
        if summary is None:
            return []
        return [item.job_id for item in summary.results if item.job_id]
