from __future__ import annotations

from astrbot.api import logger

from ..config import PaperOSConfig
from .core_client import CoreAPIError, CoreClient
from .core_query import build_core_queries
from .models import PaperCandidate, PaperSearchResult, QueryKind
from .query_router import classify_query
from .ranker import rank_candidates


class PaperSearchService:
    """Reusable search service used by commands, LLM tools, RAG, and future ingestion.

    Later you can inject LocalPaperRepository here and run local-first search before
    calling external APIs. The AstrBot plugin does not need to change.
    """

    def __init__(self, cfg: PaperOSConfig):
        self.cfg = cfg
        self.core = CoreClient(cfg.core_api)

    async def find_paper(self, raw_query: str) -> PaperSearchResult:
        query = classify_query(raw_query)
        logger.debug("find paper query: {}".format(query))

        if not self.cfg.core_api.enabled:
            return PaperSearchResult(query=query, candidates=[], status="disabled", message="CORE API is disabled")

        limit = self.cfg.core_api.topic_candidate_limit if query.kind == QueryKind.TOPIC else self.cfg.core_api.default_limit
        core_queries = build_core_queries(query, enable_rewrite=self.cfg.search_policy.enable_query_rewrite)
        all_candidates: list[PaperCandidate] = []
        errors: list[str] = []

        # For CORE-only version, queries are tried from strict to broad. We stop
        # when we have a high-confidence candidate; otherwise broaden gradually.
        for cq in core_queries:
            try:
                candidates = await self.core.search_works(cq, limit=limit, sort=self.cfg.core_api.sort)
            except CoreAPIError as e:
                errors.append(str(e))
                continue
            all_candidates.extend(candidates)
            ranked_now = rank_candidates(query, all_candidates)
            accepted = self._maybe_accept(query, ranked_now)
            if accepted is not None and query.kind != QueryKind.TOPIC:
                return PaperSearchResult(query=query, candidates=ranked_now, accepted=accepted, ambiguous=False, status="ok")

        ranked = rank_candidates(query, all_candidates)
        if not ranked:
            msg = "; ".join(errors) if errors else "没有找到候选论文"
            return PaperSearchResult(query=query, candidates=[], status="not_found", message=msg)

        accepted = None if query.kind == QueryKind.TOPIC else self._maybe_accept(query, ranked)
        ambiguous = accepted is None and query.kind != QueryKind.TOPIC
        return PaperSearchResult(query=query, candidates=ranked, accepted=accepted, ambiguous=ambiguous, status="ok")

    def _maybe_accept(self, query, ranked: list[PaperCandidate]) -> PaperCandidate | None:
        if not ranked:
            return None
        top1 = ranked[0]
        if top1.score < self.cfg.search_policy.accept_min_score:
            return None
        if len(ranked) >= 2 and (top1.score - ranked[1].score) < self.cfg.search_policy.ambiguous_gap_threshold:
            return None
        return top1
