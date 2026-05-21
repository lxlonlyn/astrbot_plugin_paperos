from typing import Any

from astrbot.api import logger

from ..config import PaperOSConfig
from .acquire.fulltext_resolver import FulltextResolver
from .acquire.verifier import FulltextVerifier
from .models import PaperSearchResult
from .pipeline import PaperSearchPipeline
from .providers.core.client import CoreClient
from .providers.core.fulltext_provider import CoreFulltextProvider
from .providers.core.metadata_provider import CoreMetadataProvider
from .query.analyzer import AstrBotLLMQueryAnalyzer
from .resolve.candidate_resolver import CandidateResolver
from .resolve.dedup import PaperDeduplicator
from .resolve.disambiguator import PaperDisambiguator


class PaperSearchService:
    """Public search facade used by AstrBot handlers, tools, RAG and ingestion.

    Service is responsible for dependency assembly and stable public methods.
    Pipeline is responsible for search-stage orchestration.
    """

    def __init__(self, cfg: PaperOSConfig, astrbot_context: Any):
        self.cfg = cfg
        self.core_client = CoreClient(cfg.core_api)

        query_analyzer = AstrBotLLMQueryAnalyzer(
            cfg=cfg,
            context=astrbot_context,
        )
        metadata_resolver = CandidateResolver(
            providers=[CoreMetadataProvider(self.core_client)]
        )
        fulltext_resolver = FulltextResolver(
            providers=[CoreFulltextProvider()]
        )

        self.pipeline = PaperSearchPipeline(
            cfg=cfg,
            query_analyzer=query_analyzer,
            metadata_resolver=metadata_resolver,
            deduplicator=PaperDeduplicator(),
            disambiguator=PaperDisambiguator(cfg.search_policy),
            fulltext_resolver=fulltext_resolver,
            verifier=FulltextVerifier(cfg.search_policy),
        )
        logger.debug("[PaperOS][SearchService] initialized metadata_providers=[core] fulltext_providers=[core]")

    async def search(self, raw_query: str, *, event=None, need_fulltext: bool = True) -> PaperSearchResult:
        """Search papers from natural-language query.

        This is the only method other PaperOS modules should call.
        """
        return await self.pipeline.run(
            raw_query=raw_query,
            event=event,
            need_fulltext=need_fulltext,
        )

    async def find_paper(self, raw_query: str, *, event=None) -> PaperSearchResult:
        """Backward-compatible alias for old command/tool code."""
        return await self.search(raw_query, event=event, need_fulltext=True)

    async def aclose(self) -> None:
        await self.pipeline.aclose()
        await self.core_client.aclose()
