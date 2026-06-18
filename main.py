from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.utils.session_waiter import SessionController, session_waiter
import astrbot.api.message_components as Comp

from .paperos.app import PaperOSApp, PaperOSCommandResponse
from .paperos.config import load_config
from .paperos.utils.astrbot_files import (
    copy_pdf_to_upload_tmp,
    event_has_file_message,
    extract_local_pdf_from_event,
)


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
        logger.info("[PaperOS] plugin initialized")

    async def terminate(self):
        await self.os.close()
        logger.info("[PaperOS] plugin terminated")

    # ================= helper func =================
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
    
    # ================= PaperOS commands =================
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
        """从本地 chunks 做 RAG evidence 检索，优先 hybrid，失败时回退 FTS。"""
        query_text = self._extract_after_command(
            event.message_str.strip(),
            command_candidates=["/paperos rag", "paperos rag"],
        )
        response = await self.os.rag(query_text)
        yield self._to_astrbot_result(event, response)

    # ================= upload probe =================
    @paperos.command("upload")
    async def upload_probe(self, event: AstrMessageEvent):
        """等待用户发送 PDF，只探测 AstrBot 文件接收和 GROBID 通路。"""
        yield event.plain_result(
            "PaperOS Upload Probe\n"
            "请在 5 分钟内发送 PDF。\n"
            "本步骤只调用已配置的 GROBID，不搜索、不调用大模型、不入库、不建 RAG。"
        )

        @session_waiter(timeout=300, record_history_chains=False)
        async def wait_pdf(controller: SessionController, next_event: AstrMessageEvent):
            text = (next_event.message_str or "").strip().lower()
            if text in {"取消", "cancel", "退出"}:
                await next_event.send(next_event.plain_result("已取消 PDF 上传测试。"))
                controller.stop()
                return

            ref = extract_local_pdf_from_event(next_event)
            if ref is None:
                if event_has_file_message(next_event):
                    message = "检测到文件消息，但当前平台没有提供本地 PDF 文件路径；本次 upload probe 暂不下载远程文件。"
                else:
                    message = "没有检测到本地 PDF 文件。请直接发送 PDF，或输入「取消」。"
                await next_event.send(next_event.plain_result(message))
                controller.keep(timeout=300, reset_timeout=True)
                return

            tmp_dir = await self.os.upload_tmp_dir()
            if tmp_dir is None:
                await next_event.send(
                    next_event.plain_result(
                        "PaperOS Upload Probe\n- ERROR storage 未启用，无法使用 GROBID 配置。"
                    )
                )
                controller.stop()
                return

            try:
                pdf_path = copy_pdf_to_upload_tmp(
                    ref,
                    tmp_dir=tmp_dir,
                    max_size_mb=self.os.cfg.search_policy.max_pdf_size_mb,
                )
                response = await self.os.upload_probe(pdf_path)
            except Exception as exc:
                await next_event.send(next_event.plain_result(f"PaperOS Upload Probe\n- ERROR {exc}"))
                controller.stop()
                return

            await next_event.send(self._to_astrbot_result(next_event, response))
            controller.stop()

        try:
            await wait_pdf(event)
        except TimeoutError:
            yield event.plain_result("PDF 上传等待超时。请重新执行 /paperos upload。")
        finally:
            stop_event = getattr(event, "stop_event", None)
            if callable(stop_event):
                stop_event()

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
