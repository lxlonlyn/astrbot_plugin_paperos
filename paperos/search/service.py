from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ..config import PaperOSConfig
from .acquire.verifier import FulltextVerifier
from .crawl.domain_resolver import DomainResolver
from .crawl.targeted import TargetedPaperCrawler
from .models import PaperSearchResult
from .pipeline import PaperSearchPipeline
from .query.analyzer import AstrBotLLMQueryAnalyzer
from .resolve.dedup import PaperDeduplicator
from .resolve.disambiguator import PaperDisambiguator


class PaperSearchService:
    """Public search facade used by AstrBot handlers/tools.

    SearchService performs online acquisition only. It never writes SQLite and
    never builds embeddings. The corrected stage has no generic web-search
    backend and no academic API main path.
    """

    def __init__(self, cfg: PaperOSConfig, astrbot_context: Any):
        self.cfg = cfg
        query_analyzer = AstrBotLLMQueryAnalyzer(cfg=cfg, context=astrbot_context)
        crawler = TargetedPaperCrawler(
            crawler_cfg=cfg.crawler,
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
            "[PaperOS][SearchService] initialized strategy=llm_direct_source_crawler crawler_enabled=%s core_enabled=%s",
            cfg.crawler.enabled,
            cfg.core_api.enabled,
        )

    async def search(self, raw_query: str, *, event=None, need_fulltext: bool = True) -> PaperSearchResult:
        """Search papers from a natural-language request.

        The LLM may propose concrete source URLs/IDs. The crawler verifies and
        downloads candidates. Persistence is still the storage module's job.
        """
        return await self.pipeline.run(raw_query=raw_query, event=event, need_fulltext=need_fulltext)

    async def find_paper(self, raw_query: str, *, event=None) -> PaperSearchResult:
        """Backward-compatible alias for old command/tool code."""
        return await self.search(raw_query, event=event, need_fulltext=True)

    async def aclose(self) -> None:
        await self.pipeline.aclose()
