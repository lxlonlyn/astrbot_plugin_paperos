from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ..config import PaperOSConfig
from .acquire.verifier import FulltextVerifier
from .crawl.domain_resolver import DomainResolver
from .crawl.search_engine import DuckDuckGoHTMLSearchEngine
from .crawl.targeted import TargetedPaperCrawler
from .models import PaperSearchResult
from .pipeline import PaperSearchPipeline
from .query.analyzer import AstrBotLLMQueryAnalyzer
from .resolve.dedup import PaperDeduplicator
from .resolve.disambiguator import PaperDisambiguator


class PaperSearchService:
    """Public search facade used by AstrBot handlers/tools.

    SearchService performs online discovery and temporary acquisition only. It
    never writes SQLite and never builds embeddings. Storage/RAG should not call
    this service directly.
    """

    def __init__(self, cfg: PaperOSConfig, astrbot_context: Any):
        self.cfg = cfg
        query_analyzer = AstrBotLLMQueryAnalyzer(cfg=cfg, context=astrbot_context)
        search_engine = DuckDuckGoHTMLSearchEngine(cfg.web_search)
        crawler = TargetedPaperCrawler(
            crawler_cfg=cfg.crawler,
            web_cfg=cfg.web_search,
            search_engine=search_engine,
            domain_resolver=DomainResolver(),
        )
        self.pipeline = PaperSearchPipeline(
            cfg=cfg,
            query_analyzer=query_analyzer,
            crawler=crawler,
            deduplicator=PaperDeduplicator(),
            disambiguator=PaperDisambiguator(cfg.search_policy),
            verifier=FulltextVerifier(cfg.search_policy),
        )
        logger.debug(
            "[PaperOS][SearchService] initialized strategy=llm_web_targeted_crawler web_backend=%s academic_api_fallback=%s",
            cfg.web_search.backend,
            cfg.crawler.academic_api_fallback,
        )

    async def search(self, raw_query: str, *, event=None, need_fulltext: bool = True) -> PaperSearchResult:
        """Search papers from natural-language query.

        The result may include verified local PDFs in `FulltextLocation.local_path`,
        but persistence is still the storage module's job.
        """

        return await self.pipeline.run(raw_query=raw_query, event=event, need_fulltext=need_fulltext)

    async def find_paper(self, raw_query: str, *, event=None) -> PaperSearchResult:
        """Backward-compatible alias for old command/tool code."""

        return await self.search(raw_query, event=event, need_fulltext=True)

    async def aclose(self) -> None:
        await self.pipeline.aclose()
