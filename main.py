from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

from .paperos.config import load_config
from .paperos.search.models import PaperCandidate, PaperSearchResult, QueryKind
from .paperos.search.service import PaperSearchService


class PaperOSPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.cfg = load_config(config)
        self.search_service = PaperSearchService(self.cfg)
        logger.info("PaperOS plugin initialized")

    @filter.command_group("paperos")
    def paperos(self):
        """PaperOS 指令组。"""
        pass

    @paperos.command("search")
    async def search_paper(self, event: AstrMessageEvent):
        """搜索论文。

        用法：/paperos search attention is all you need
        """
        raw_query = event.message_str.strip().lower()
        prefix = "paperos search"
        if raw_query.startswith(prefix):
            query_text = raw_query[len(prefix):].strip()
        else:
            raise KeyError("prefix={} not found in query_message={}? why?".format(prefix, raw_query))
        
        result = await self.search_service.find_paper(query_text)
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
            f"- 思考 Provider: {self.cfg.general.thinking_provider_id or '回退到通用 Provider'}"
        )

    @filter.llm_tool(name="paperos_search_paper")
    async def paperos_search_paper_tool(self, event: AstrMessageEvent, query: str) -> str:
        '''搜索学术论文，并返回候选论文列表。

        Args:
            query(string): 论文链接、DOI、arXiv ID、准确标题、模糊标题或研究话题。
        '''
        result = await self.search_service.find_paper(query)
        return self._format_search_result(result, compact=True)

    def _format_search_result(self, result: PaperSearchResult, *, compact: bool = False) -> str:
        if result.status == "disabled":
            return "CORE API 当前未启用。"
        if result.status in {"not_found", "error"} or not result.candidates:
            return f"没有找到合适的论文。{result.message}".strip()

        if result.query.kind == QueryKind.TOPIC:
            limit = min(len(result.candidates), self.cfg.search_policy.max_return_candidates)
            lines = [f"话题检索：{result.query.raw}", f"找到 {len(result.candidates)} 个候选，优先展示前 {limit} 个："]
            for i, cand in enumerate(result.candidates[:limit], 1):
                lines.append(self._format_candidate(cand, i=i, compact=compact))
            return "\n".join(lines)

        if result.accepted:
            return "高置信匹配：\n" + self._format_candidate(result.accepted, compact=compact)

        limit = min(len(result.candidates), self.cfg.search_policy.max_return_candidates)
        lines = [
            "可能存在多个候选，建议人工确认：",
            f"检索类型：{result.query.kind.value}",
        ]
        for i, cand in enumerate(result.candidates[:limit], 1):
            lines.append(self._format_candidate(cand, i=i, compact=compact))
        return "\n".join(lines)

    def _format_candidate(self, cand: PaperCandidate, *, i: int | None = None, compact: bool = False) -> str:
        prefix = f"{i}. " if i is not None else ""
        authors = ", ".join(cand.authors[:3])
        if len(cand.authors) > 3:
            authors += " et al."

        parts = [
            f"{prefix}{cand.title}",
            f"   年份：{cand.year or '未知'}；分数：{cand.score:.2f}；来源：{cand.source}",
        ]
        if authors:
            parts.append(f"   作者：{authors}")
        if cand.doi:
            parts.append(f"   DOI：{cand.doi}")
        if cand.arxiv_id:
            parts.append(f"   arXiv：{cand.arxiv_id}")
        if cand.core_id:
            parts.append(f"   CORE ID：{cand.core_id}")
        if cand.download_url:
            parts.append(f"   PDF/下载：{cand.download_url}")
        if not compact and cand.score_reason:
            parts.append(f"   匹配依据：{cand.score_reason}")
        return "\n".join(parts)

    async def terminate(self):
        logger.info("PaperOS plugin terminated")
