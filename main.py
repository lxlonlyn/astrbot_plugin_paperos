from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

from .paperos.app import PaperOSApp, PaperOSCommandResponse
from .paperos.config import load_config


class PaperOSPlugin(Star):
    """AstrBot entrypoint for PaperOS."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.os = PaperOSApp(
            cfg=load_config(config),
            astrbot_context=context,
            plugin_name=getattr(self, "name", "astrbot_plugin_paperos"),
        )
        logger.info("[PaperOS] plugin initialized")

    async def initialize(self):
        self.os.plugin_name = getattr(self, "name", self.os.plugin_name)
        await self.os.initialize()
        logger.info("[PaperOS] plugin initilized")

    async def terminate(self):
        await self.os.close()
        logger.info("[PaperOS] plugin terminated")

    # ================= PaperOS 指令开始 =================
    @filter.command_group("paperos")
    def paperos():
        """PaperOS 指令组。"""
        pass

    # ================= config =================
    @paperos.command("config")
    async def show_config(self, event: AstrMessageEvent):
        """显示 PaperOS 当前关键配置。"""
        yield event.plain_result(self.os.config_text())
    
    # ================= search =================
    @paperos.command("search")
    async def search_paper(self, event: AstrMessageEvent):
        """搜索论文并尝试返回合格 PDF。"""
        raw_message = event.message_str.strip()
        query_text = self._extract_after_command(
            raw_message,
            command_candidates=["/paperos search", "paperos search"],
        )

        logger.debug("[PaperOS] command discovery raw=%r query=%r", raw_message, query_text)
        response = await self.os.search(query_text, event=event)
        yield self._to_astrbot_result(event, response)

    # ================= rag =================
    @paperos.command("rag")
    async def rag_local(self, event: AstrMessageEvent):
        """从本地 chunks 做 FTS-only RAG evidence 检索。"""
        query_text = self._extract_after_command(
            event.message_str.strip(),
            command_candidates=["/paperos rag", "paperos rag"],
        )
        response = await self.os.rag(query_text)
        yield self._to_astrbot_result(event, response)

    # ================= storage =================
    @paperos.group("storage")
    def paperos_storage():
        """PaperOS storage 指令组。"""
        pass

    @paperos_storage.command("status")
    async def storage_status(self, event: AstrMessageEvent):
        """显示 PaperOS storage 状态与统计。"""
        response = await self.os.storage_status()
        yield self._to_astrbot_result(event, response)

    @paperos_storage.command("info")
    async def storage_info(self, event: AstrMessageEvent):
        """按 paper_id、DOI、arXiv ID 或标题查询本地论文信息。"""
        query_text = self._extract_after_command(
            event.message_str.strip(),
            command_candidates=["/paperos storage info", "paperos storage info"],
        )
        response = await self.os.storage_info(query_text)
        yield self._to_astrbot_result(event, response)

    def _extract_after_command(self, raw: str, command_candidates: list[str]) -> str:
        raw_l = raw.lower()
        for cmd in command_candidates:
            cmd_l = cmd.lower()
            if raw_l.startswith(cmd_l):
                return raw[len(cmd):].strip()
        return raw.strip()

    def _to_astrbot_result(self, event: AstrMessageEvent, response: PaperOSCommandResponse):
        if response.file_path:
            return event.chain_result([
                Comp.Plain(response.text),
                Comp.File(file=response.file_path, name=response.file_name or "paper.pdf"),
            ])
        return event.plain_result(response.text)

