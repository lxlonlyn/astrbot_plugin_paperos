from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .config import PaperOSConfig
from .rag.indexing import RagIndexService
from .rag.models import RagFilters
from .rag.presenter import RagPresenter
from .rag.service import RagService
from .search.models import PaperSearchResult
from .search.presenter import PaperSearchPresenter
from .search.service import PaperSearchService
from .storage.diagnostics import StorageDiagnostics
from .storage.factory import PaperOSStorageContext, create_storage_context
from .storage.presenter import StoragePresenter
from .workflows.paper_discovery import PaperDiscoveryWorkflow
from .workflows.search_storage import SearchStorageImportSummary, SearchStorageImportWorkflow


@dataclass(frozen=True)
class PaperOSCommandResponse:
    text: str
    file_path: str | None = None
    file_name: str | None = None


class PaperOSApp:
    """Application facade for PaperOS command/tool operations.

    This class owns service/workflow/presenter assembly. AstrBot-specific
    command registration and result conversion stay in `main.py`.
    """

    def __init__(
        self,
        *,
        cfg: PaperOSConfig,
        astrbot_context: Any,
        plugin_name: str = "astrbot_plugin_paperos",
    ):
        self.cfg = cfg
        self.astrbot_context = astrbot_context
        self.plugin_name = plugin_name
        self.search_service = PaperSearchService(
            cfg=cfg,
            astrbot_context=astrbot_context,
        )
        self.search_presenter = PaperSearchPresenter(cfg)
        self.rag_presenter = RagPresenter()
        self.storage_presenter = StoragePresenter()
        self.storage: PaperOSStorageContext | None = None

    async def initialize(self) -> None:
        await self._ensure_storage_context()

    async def search(self, query_text: str, *, event: Any | None = None) -> PaperOSCommandResponse:
        if not query_text:
            return PaperOSCommandResponse("用法：/paperos search attention is all you need")

        logger.debug("[PaperOS] command discovery query=%r", query_text)
        discovery = await self._discover(query_text, event=event)
        result = discovery.search_result
        import_summary = discovery.import_summary
        logger.debug(
            "[PaperOS] discovery done papers=%d pdfs=%d parse_jobs=%d query=%r",
            discovery.imported_count,
            discovery.pdf_count,
            len(discovery.storage_parse_job_ids),
            query_text,
        )

        text = self._format_discovery_response(discovery)
        pdf = self._first_verified_pdf(result)
        stored_pdf_path = self._first_imported_pdf_path(import_summary)
        send_path = self._first_existing_path(
            stored_pdf_path,
            pdf.local_path if pdf is not None else None,
        )
        if not send_path:
            return PaperOSCommandResponse(text)

        file_name = pdf.filename if pdf is not None and pdf.filename else "paper.pdf"
        return PaperOSCommandResponse(
            text=text + "\n\n已取得合格 PDF，尝试发送文件：",
            file_path=send_path,
            file_name=file_name,
        )

    async def rag(self, query_text: str) -> PaperOSCommandResponse:
        if not query_text:
            return PaperOSCommandResponse("用法：/paperos rag attention mechanism")

        storage = await self._ensure_storage_context()
        if storage is None:
            return PaperOSCommandResponse("PaperOS RAG\n- WARN storage config disabled")

        rag = self._build_rag_service(storage)
        pack = await rag.retrieve_evidence(query_text, filters=RagFilters(limit=8))
        return PaperOSCommandResponse(self.rag_presenter.format_evidence_pack(pack))

    async def storage_status(self) -> PaperOSCommandResponse:
        storage = await self._ensure_storage_context()
        if storage is None:
            return PaperOSCommandResponse("PaperOS Storage Status\n- WARN enabled: storage config disabled")

        diagnostics = self._build_storage_diagnostics(storage)
        status = diagnostics.status(enabled=self.cfg.storage.enabled)
        return PaperOSCommandResponse(self.storage_presenter.format_status(status))

    async def storage_info(self, query_text: str) -> PaperOSCommandResponse:
        if not query_text:
            return PaperOSCommandResponse("用法：/paperos storage info <paper_id|doi|arxiv|title>")

        storage = await self._ensure_storage_context()
        if storage is None:
            return PaperOSCommandResponse("PaperOS Storage Info\n- WARN enabled: storage config disabled")

        diagnostics = self._build_storage_diagnostics(storage)
        info = diagnostics.paper_info(query_text)
        return PaperOSCommandResponse(self.storage_presenter.format_info(info))

    def config_text(self) -> str:
        return self.search_presenter.format_config()

    async def search_tool(self, query: str, *, event: Any | None = None) -> str:
        result = await self.search_service.search(
            raw_query=query,
            event=event,
            need_fulltext=True,
        )
        return self.search_presenter.format_search_result(result, compact=True)

    async def close(self) -> None:
        if self.storage is not None:
            await self.storage.aclose()
        await self.search_service.aclose()

    async def _discover(self, query_text: str, *, event: Any | None = None):
        workflow, auto_import = await self._build_discovery_workflow()
        discovery = await workflow.discover_and_index(
            query_text,
            event=event,
            need_fulltext=True,
            auto_import=auto_import,
            selection="selected",
            process_document=True,
            cleanup_temporary_pdf=False,
            ignore_import_errors=True,
        )
        if discovery.import_error:
            logger.warning(
                "[PaperOS] discovery storage import failed query=%r: %s",
                query_text,
                discovery.import_error,
            )
        return discovery

    async def _build_discovery_workflow(self) -> tuple[PaperDiscoveryWorkflow, bool]:
        storage = await self._ensure_storage_context()
        if storage is None:
            return PaperDiscoveryWorkflow(search_service=self.search_service), False

        return (
            PaperDiscoveryWorkflow(
                search_service=self.search_service,
                search_storage=self._build_search_storage_workflow(storage),
                rag_index_service=self._build_rag_index_service(storage),
            ),
            True,
        )

    def _build_search_storage_workflow(
        self,
        storage: PaperOSStorageContext,
    ) -> SearchStorageImportWorkflow:
        return SearchStorageImportWorkflow(
            repository=storage.repository,
            object_store=storage.object_store,
            storage_cfg=storage.cfg,
        )

    def _build_rag_index_service(self, storage: PaperOSStorageContext) -> RagIndexService:
        return RagIndexService(
            repository=storage.repository,
            vector_index=storage.vector_index,
            context=self.astrbot_context,
            cfg=self.cfg.rag,
        )

    def _build_rag_service(self, storage: PaperOSStorageContext) -> RagService:
        return RagService(
            repository=storage.repository,
            vector_index=storage.vector_index,
            context=self.astrbot_context,
            cfg=self.cfg.rag,
        )

    def _build_storage_diagnostics(self, storage: PaperOSStorageContext) -> StorageDiagnostics:
        return StorageDiagnostics(storage)

    def _format_discovery_response(self, discovery) -> str:
        text = self.search_presenter.format_search_result(discovery.search_result)
        if discovery.import_summary is not None:
            text += "\n\n" + self.storage_presenter.format_import_summary(discovery.import_summary)
        if discovery.rag_index_attempts:
            text += "\n\n" + self.storage_presenter.format_rag_index_summary(
                discovery.rag_index_attempts
            )
        return text

    def _first_verified_pdf(self, result: PaperSearchResult):
        for cand in result.selected or result.candidates:
            pdf = cand.best_verified_pdf()
            if pdf is not None:
                return pdf
        return None

    def _first_imported_pdf_path(self, summary: SearchStorageImportSummary | None) -> str | None:
        if summary is None:
            return None
        for item in summary.results:
            if item.imported_pdf and item.object_path:
                return item.object_path
        return None

    def _first_existing_path(self, *paths: str | None) -> str | None:
        for path in paths:
            if not path:
                continue
            candidate = Path(path)
            if candidate.exists():
                return str(candidate.resolve())
            logger.warning("[PaperOS] skip missing file path before sending: %s", path)
        return None

    async def _ensure_storage_context(self) -> PaperOSStorageContext | None:
        if not self.cfg.storage.enabled:
            return None
        if self.storage is None:
            self.storage = await create_storage_context(self.cfg, plugin_name=self.plugin_name)
        return self.storage
