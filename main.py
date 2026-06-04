from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

from .paperos.config import load_config
from .paperos.search.models import PaperSearchResult
from .paperos.search.presenter import PaperSearchPresenter
from .paperos.search.service import PaperSearchService
from .paperos.storage.diagnostics import StorageDiagnostics
from .paperos.storage.factory import PaperOSStorageContext, create_storage_context
from .paperos.storage.presenter import StoragePresenter
from .paperos.workflows.paper_discovery import PaperDiscoveryWorkflow
from .paperos.workflows.search_storage import SearchStorageImportSummary, SearchStorageImportWorkflow


@filter.command_group("paperos")
def paperos():
    """PaperOS 指令组。"""
    pass


@paperos.group("storage")
def paperos_storage():
    """PaperOS storage 指令组。"""
    pass


class PaperOSPlugin(Star):
    """AstrBot entrypoint for PaperOS."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.cfg = load_config(config)
        self.search_service = PaperSearchService(
            cfg=self.cfg,
            astrbot_context=context,
        )
        self.presenter = PaperSearchPresenter(self.cfg)
        self.storage_presenter = StoragePresenter()
        self.storage: PaperOSStorageContext | None = None
        logger.info("[PaperOS] plugin initialized")

    async def initialize(self):
        await self._ensure_storage_context()

    @paperos.command("search")
    async def search_paper(self, event: AstrMessageEvent):
        """搜索论文并尝试返回合格 PDF。"""
        raw_message = event.message_str.strip()
        query_text = self._extract_after_command(
            raw_message,
            command_candidates=["/paperos search", "paperos search"],
        )

        if not query_text:
            yield event.plain_result("用法：/paperos search attention is all you need")
            return

        logger.debug("[PaperOS] command discovery raw=%r query=%r", raw_message, query_text)
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

        pdf = self._first_verified_pdf(result)
        stored_pdf_path = self._first_imported_pdf_path(import_summary)
        text = self.presenter.format_search_result(result)
        if import_summary is not None:
            text += "\n\n" + self.storage_presenter.format_import_summary(import_summary)

        send_path = stored_pdf_path or (pdf.local_path if pdf is not None else None)
        if send_path:
            yield event.chain_result([
                Comp.Plain(text + "\n\n已取得合格 PDF，尝试发送文件："),
                Comp.File(file=send_path, name=(pdf.filename if pdf is not None and pdf.filename else "paper.pdf")),
            ])
        else:
            yield event.plain_result(text)

    @paperos.command("config")
    async def show_config(self, event: AstrMessageEvent):
        """显示 PaperOS 当前关键配置。"""
        yield event.plain_result(self.presenter.format_config())

    @paperos_storage.command("status")
    async def storage_status(self, event: AstrMessageEvent):
        """显示 PaperOS storage 状态与统计。"""
        storage = await self._ensure_storage_context()
        if storage is None:
            yield event.plain_result("PaperOS Storage Status\n- WARN enabled: storage config disabled")
            return

        diagnostics = StorageDiagnostics(storage)
        status = diagnostics.status(enabled=self.cfg.storage.enabled)
        yield event.plain_result(self.storage_presenter.format_status(status))

    @paperos_storage.command("info")
    async def storage_info(self, event: AstrMessageEvent):
        """按 paper_id、DOI、arXiv ID 或标题查询本地论文信息。"""
        query_text = self._extract_after_command(
            event.message_str.strip(),
            command_candidates=["/paperos storage info", "paperos storage info"],
        )
        if not query_text:
            yield event.plain_result("用法：/paperos storage info <paper_id|doi|arxiv|title>")
            return

        storage = await self._ensure_storage_context()
        if storage is None:
            yield event.plain_result("PaperOS Storage Info\n- WARN enabled: storage config disabled")
            return

        diagnostics = StorageDiagnostics(storage)
        info = diagnostics.paper_info(query_text)
        yield event.plain_result(self.storage_presenter.format_info(info))

    @filter.llm_tool(name="paperos_search_paper")
    async def paperos_search_paper_tool(self, event: AstrMessageEvent, query: str) -> str:
        """搜索学术论文，并返回候选论文列表。

        Args:
            query(string): 论文链接、DOI、arXiv ID、准确标题、模糊标题或研究话题。
        """
        result = await self.search_service.search(
            raw_query=query,
            event=event,
            need_fulltext=True,
        )
        return self.presenter.format_search_result(result, compact=True)

    def _first_verified_pdf(self, result: PaperSearchResult):
        for cand in result.selected or result.candidates:
            pdf = cand.best_verified_pdf()
            if pdf is not None:
                return pdf
        return None

    async def _discover(self, query_text: str, *, event: AstrMessageEvent):
        search_storage = None
        storage = await self._ensure_storage_context()
        if storage is not None:
            search_storage = SearchStorageImportWorkflow(
                repository=storage.repository,
                object_store=storage.object_store,
            )
        workflow = PaperDiscoveryWorkflow(
            search_service=self.search_service,
            search_storage=search_storage,
        )
        discovery = await workflow.discover_and_index(
            query_text,
            event=event,
            need_fulltext=True,
            auto_import=search_storage is not None,
            selection="selected",
            cleanup_temporary_pdf=True,
            ignore_import_errors=True,
        )
        if discovery.import_error:
            logger.warning(
                "[PaperOS] discovery storage import failed query=%r: %s",
                query_text,
                discovery.import_error,
            )
        return discovery

    def _first_imported_pdf_path(self, summary: SearchStorageImportSummary | None) -> str | None:
        if summary is None:
            return None
        for item in summary.results:
            if item.imported_pdf and item.object_path:
                return item.object_path
        return None

    def _extract_after_command(self, raw: str, command_candidates: list[str]) -> str:
        raw_l = raw.lower()
        for cmd in command_candidates:
            cmd_l = cmd.lower()
            if raw_l.startswith(cmd_l):
                return raw[len(cmd):].strip()
        return raw.strip()

    async def _ensure_storage_context(self) -> PaperOSStorageContext | None:
        if not self.cfg.storage.enabled:
            return None
        if self.storage is None:
            plugin_name = getattr(self, "name", "astrbot_plugin_paperos")
            self.storage = await create_storage_context(self.cfg, plugin_name=plugin_name)
        return self.storage

    async def terminate(self):
        if self.storage is not None:
            await self.storage.aclose()
        await self.search_service.aclose()
        logger.info("[PaperOS] plugin terminated")
