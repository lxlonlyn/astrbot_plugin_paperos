from __future__ import annotations

from typing import Any

from ..config import PaperOSConfig
from .acquire.fulltext_resolver import FulltextResolver
from .acquire.verifier import FulltextVerifier
from .pipeline import PaperSearchPipeline
from .providers.core.client import CoreClient
from .providers.core.fulltext_provider import CoreFulltextProvider
from .providers.core.metadata_provider import CoreMetadataProvider
from .query.analyzer import AstrBotLLMQueryAnalyzer
from .resolve.candidate_resolver import CandidateResolver
from .resolve.dedup import PaperDeduplicator
from .resolve.disambiguator import PaperDisambiguator


class PaperSearchService:
    """Public entry point for PaperOS search.

    RAG / reasoning / user commands should call this service instead of calling
    provider clients directly.
    """

    def __init__(self, cfg: PaperOSConfig, astrbot_context: Any):
        self.cfg = cfg
        self.core_client = CoreClient(cfg.core_api)
        self.query_analyzer = AstrBotLLMQueryAnalyzer(context=astrbot_context, cfg=cfg)
        self.metadata_resolver = CandidateResolver(
            providers=[
                CoreMetadataProvider(self.core_client),
            ]
        )
        self.fulltext_resolver = FulltextResolver(
            providers=[
                CoreFulltextProvider(self.core_client),
            ]
        )
        self.pipeline = PaperSearchPipeline(
            query_analyzer=self.query_analyzer,
            metadata_resolver=self.metadata_resolver,
            deduplicator=PaperDeduplicator(),
            disambiguator=PaperDisambiguator(cfg.search_policy),
            fulltext_resolver=self.fulltext_resolver,
            verifier=FulltextVerifier(cfg.search_policy),
            cfg=cfg,
        )

    async def search(self, raw_query: str, *, event: Any | None = None, need_fulltext: bool = True):
        return await self.pipeline.run(raw_query, event=event, need_fulltext=need_fulltext)

    # Backward-compatible wrapper for your previous command/tool code.
    async def find_paper(self, raw_query: str, *, event: Any | None = None):
        return await self.search(raw_query, event=event, need_fulltext=True)

    async def aclose(self) -> None:
        await self.core_client.aclose()
