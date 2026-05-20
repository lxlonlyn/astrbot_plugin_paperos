from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .paperos.config import load_config
from .paperos.search.models import PaperCandidate, PaperSearchResult
from .paperos.search.service import PaperSearchService


class PaperOSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.cfg = load_config(config)
        self.search_service = PaperSearchService(
            cfg=self.cfg,
            astrbot_context=context
        )
        logger.info("PaperOS plugin initialized")

    @filter.command_group("paperos")
    def paperos(self):
        """PaperOS 指令组。"""
        pass

    @paperos.command("search")
    async def search_paper(self, event: AstrMessageEvent):
        """搜索论文。

        用法：
        /paperos search attention is all you need
        /paperos search 注意力机制的奠基文章
        /paperos search https://doi.org/10.1145/3528223.3530127
        """
        raw_message = event.message_str.strip()
        query_text = self._extract_after_command(
            raw_message,
            command_candidates=["/paperos search", "paperos search"],
        )
        if not query_text:
            yield event.plain_result("用法：/paperos search attention is all you need")
            return

        logger.debug(f"[PaperOS] 原始询问: {query_text!r}")

        result = await self.search_service.search(
            raw_query=query_text,
            event=event,
            need_fulltext=True,
        )
        yield event.plain_result(self._format_search_result(result))

    @paperos.command("config")
    async def show_config(self, event: AstrMessageEvent):
        """显示 PaperOS 当前关键配置。"""
        key_state = "已配置" if self.cfg.core_api.api_key else "未配置"
        yield event.plain_result(
            "PaperOS 配置：\n"
            f"- CORE API: {'启用' if self.cfg.core_api.enabled else '禁用'}\n"
            f"- CORE API Key: {key_state}\n"
            f"- 通用 Provider: {self.cfg.general.default_provider_id or '使用当前会话默认'}\n"
            f"- 思考 Provider: {self.cfg.general.thinking_provider_id or '回退到通用 Provider'}\n"
            f"- LLM QueryAnalyzer: {'启用' if self.cfg.query_analyzer.enabled else '禁用'}"
        )

    # @filter.llm_tool(name="paperos_search_paper")
    # async def paperos_search_paper_tool(self, event: AstrMessageEvent, query: str) -> str:
    #     """搜索学术论文，并返回候选论文列表。

    #     Args:
    #         query(string): 论文链接、DOI、arXiv ID、准确标题、模糊标题或研究话题。
    #     """
    #     result = await self.search_service.search(
    #         raw_query=query,
    #         event=event,
    #         need_fulltext=True,
    #     )
    #     return self._format_search_result(result, compact=True)

    def _extract_after_command(self, raw: str, command_candidates: list[str]) -> str:
        raw_l = raw.lower()
        for cmd in command_candidates:
            cmd_l = cmd.lower()
            if raw_l.startswith(cmd_l):
                return raw[len(cmd):].strip()
        return raw.strip()

    def _format_search_result(self, result: PaperSearchResult, *, compact: bool = False) -> str:
        if result.status == "disabled":
            return "CORE API 当前未启用。"

        header: list[str] = []
        if result.plan is not None:
            header.append(f"解析意图：{result.plan.intent.value}")
            if result.plan.translated_query:
                header.append(f"英文/规范化检索：{result.plan.translated_query}")
            if result.plan.hypotheses:
                kinds = ", ".join(h.kind.value for h in result.plan.hypotheses[:4])
                header.append(f"检索假设：{kinds}")

        if result.status in {"not_found", "error"} or not result.candidates:
            body = f"没有找到合适的论文。{result.message}".strip()
            return "\n".join(header + [body]) if header else body

        display_items = result.selected or result.candidates
        limit = min(len(display_items), self.cfg.search_policy.max_return_candidates)

        if result.selected:
            lines = header + [f"选中 {len(result.selected)} 篇，展示前 {limit} 篇："]
        else:
            lines = header + ["可能存在多个候选，建议人工确认：", f"候选数量：{len(result.candidates)}"]

        for i, cand in enumerate(display_items[:limit], 1):
            lines.append(self._format_candidate(cand, i=i, compact=compact))
        return "\n".join(lines)

    def _format_candidate(self, cand: PaperCandidate, *, i: int | None = None, compact: bool = False) -> str:
        prefix = f"{i}. " if i is not None else ""
        authors = ", ".join(cand.authors[:3])
        if len(cand.authors) > 3:
            authors += " et al."

        parts = [
            f"{prefix}{cand.title or '(无标题)'}",
            f" 年份：{cand.year or '未知'}；分数：{cand.score:.2f}；来源：{cand.source}",
        ]
        if authors:
            parts.append(f" 作者：{authors}")
        if cand.venue:
            parts.append(f" 期刊/会议/来源：{cand.venue}")
        if cand.doi:
            parts.append(f" DOI：{cand.doi}")
        if cand.arxiv_id:
            parts.append(f" arXiv：{cand.arxiv_id}")
        if cand.core_id:
            parts.append(f" CORE ID：{cand.core_id}")

        verified = [loc for loc in cand.fulltext_locations if loc.status == "verified_pdf"]
        if verified:
            parts.append(f" 已验证 PDF：{verified[0].url}")
        elif cand.download_url:
            parts.append(f" PDF/下载候选：{cand.download_url}")
        elif cand.landing_url:
            parts.append(f" Landing：{cand.landing_url}")

        if not compact and cand.score_reason:
            parts.append(f" 匹配依据：{cand.score_reason}")
        return "\n".join(parts)

    async def terminate(self):
        await self.search_service.aclose()
        logger.info("PaperOS plugin terminated")
