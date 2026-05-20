from __future__ import annotations

from astrbot.api import logger

from ...models import SearchIntent, SearchPlan, PaperCandidate
from .client import CoreAPIError, CoreClient
from .query_builder import build_core_queries_for_hypothesis


class CoreMetadataProvider:
    name = "core"

    def __init__(self, client: CoreClient):
        self.client = client

    async def resolve(self, plan: SearchPlan) -> list[PaperCandidate]:
        limit = plan.max_candidates
        if plan.intent == SearchIntent.TOPIC_DISCOVERY:
            limit = min(max(plan.max_candidates, 10), 50)

        all_candidates: list[PaperCandidate] = []
        for hyp in plan.hypotheses:
            queries = build_core_queries_for_hypothesis(hyp, plan)
            for q in queries:
                try:
                    candidates = await self.client.search_works(q, limit=limit)
                    all_candidates.extend(candidates)
                    # Specific search: once a strict query gives candidates, let scoring/disambiguation handle them.
                    if candidates and plan.intent != SearchIntent.TOPIC_DISCOVERY:
                        break
                except CoreAPIError as exc:
                    logger.warning(f"[PaperOS][CORE] query failed {q!r}: {exc}")
            if all_candidates and plan.intent != SearchIntent.TOPIC_DISCOVERY:
                break
        return all_candidates
