from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .paperos.config import load_config
from .paperos.search.presenter import PaperSearchPresenter
from .paperos.search.service import PaperSearchService


@filter.command_group("paperos")
def paperos():
    """PaperOS 指令组。"""
    pass


class PaperOSPlugin(Star):
    """AstrBot entrypoint for PaperOS.

    main.py 只负责 AstrBot handler / tool 注册，以及把请求交给 PaperSearchService。
    搜索结果格式化放在 paperos.search.presenter，避免入口文件继续膨胀。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.cfg = load_config(config)
        self.search_service = PaperSearchService(
            cfg=self.cfg,
            astrbot_context=context,
        )
        self.presenter = PaperSearchPresenter(self.cfg)
        logger.info("[PaperOS] plugin initialized")

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

        logger.debug("[PaperOS] command search raw=%r query=%r", raw_message, query_text)
        result = await self.search_service.search(
            raw_query=query_text,
            event=event,
            need_fulltext=True,
        )
        yield event.plain_result(self.presenter.format_search_result(result))

    @paperos.command("config")
    async def show_config(self, event: AstrMessageEvent):
        """显示 PaperOS 当前关键配置。"""
        yield event.plain_result(self.presenter.format_config())

    @filter.llm_tool(name="paperos_search_paper")
    async def paperos_search_paper_tool(self, event: AstrMessageEvent, query: str) -> str:
        '''搜索学术论文，并返回候选论文列表。

        Args:
            query(string): 论文链接、DOI、arXiv ID、准确标题、模糊标题或研究话题。
        '''
        result = await self.search_service.search(
            raw_query=query,
            event=event,
            need_fulltext=True,
        )
        return self.presenter.format_search_result(result, compact=True)

    def _extract_after_command(self, raw: str, command_candidates: list[str]) -> str:
        raw_l = raw.lower()
        for cmd in command_candidates:
            cmd_l = cmd.lower()
            if raw_l.startswith(cmd_l):
                return raw[len(cmd):].strip()
        return raw.strip()

    async def terminate(self):
        await self.search_service.aclose()
        logger.info("[PaperOS] plugin terminated")
