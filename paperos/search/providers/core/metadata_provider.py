from astrbot.api import logger

from ..base import MetadataProvider
from ...models import PaperCandidate, SearchIntent, SearchPlan
from .client import CoreAPIError, CoreClient
from .query_builder import build_core_queries


class CoreMetadataProvider(MetadataProvider):
    name = "core"

    def __init__(self, client: CoreClient):
        self.client = client

    async def search(self, plan: SearchPlan) -> list[PaperCandidate]:
        limit = self._limit_for_plan(plan)
        queries = build_core_queries(plan)
        logger.debug(
            "[PaperOS][CoreMetadataProvider] executing %d CORE queries: %s",
            len(queries),
            self._short_query_list(queries),
        )

        all_candidates: list[PaperCandidate] = []
        for query in queries:
            try:
                candidates = await self.client.search_works(
                    query,
                    limit=limit,
                    sort=self.client.cfg.sort,
                )
            except CoreAPIError as exc:
                logger.warning("[PaperOS][CoreMetadataProvider] query failed q=%r error=%s", query, exc)
                continue
            all_candidates.extend(candidates)
        return all_candidates

    def _limit_for_plan(self, plan: SearchPlan) -> int:
        if plan.intent == SearchIntent.TOPIC_DISCOVERY:
            return max(1, min(plan.max_candidates, self.client.cfg.topic_candidate_limit))
        return max(1, min(plan.max_candidates, self.client.cfg.default_limit))

    def _short_query_list(self, queries: list[str], *, max_items: int = 5) -> str:
        shown = [q if len(q) <= 80 else q[:77] + "..." for q in queries[:max_items]]
        suffix = "" if len(queries) <= max_items else f" ... +{len(queries) - max_items}"
        return "; ".join(shown) + suffix

    async def aclose(self) -> None:
        # CoreClient is shared by metadata and future fulltext providers; service closes pipeline once.
        return None
