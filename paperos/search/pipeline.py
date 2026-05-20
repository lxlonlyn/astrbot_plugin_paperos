from __future__ import annotations

from astrbot.api import logger

from .models import PaperCandidate, PaperSearchResult, SearchPlan
from .resolve.scoring import score_candidates


class PaperSearchPipeline:
    def __init__(self, *, query_analyzer, metadata_resolver, deduplicator, disambiguator, fulltext_resolver, verifier, cfg):
        self.query_analyzer = query_analyzer
        self.metadata_resolver = metadata_resolver
        self.deduplicator = deduplicator
        self.disambiguator = disambiguator
        self.fulltext_resolver = fulltext_resolver
        self.verifier = verifier
        self.cfg = cfg

    async def run(self, raw_query: str, *, event=None, need_fulltext: bool = True) -> PaperSearchResult:
        if not self.cfg.core_api.enabled:
            return PaperSearchResult(status="disabled", message="CORE API disabled")

        plan = await self.query_analyzer.analyze(raw_query, event=event)
        plan.need_fulltext = bool(need_fulltext and plan.need_fulltext)

        logger.debug("[PaperOS] search plan: {}".format(plan))

        candidates = await self._resolve_score_dedup(plan)
        if not candidates and self.cfg.query_analyzer.max_repair_rounds > 0:
            plan = await self.query_analyzer.repair(
                raw_query,
                previous_plan=plan,
                failure_reason="metadata providers returned zero candidates",
                event=event,
            )
            candidates = await self._resolve_score_dedup(plan)

        if not candidates:
            return PaperSearchResult(status="not_found", message="metadata providers returned zero candidates", plan=plan)
        
        # logger.debug("[PaperOS] search candidates: {}".format([{"title": p.title, "source": p.source, "doi": p.doi} for p in candidates]))

        selected = self.disambiguator.select(plan, candidates)
        targets: list[PaperCandidate] = selected or candidates[: plan.final_limit]

        if plan.need_fulltext:
            for paper in targets:
                locations = await self.fulltext_resolver.resolve(paper)
                verified = []
                for loc in locations[: self.cfg.search_policy.max_fulltext_candidates]:
                    verified.append(await self.verifier.verify(loc, paper))
                paper.fulltext_locations = verified

        status = "selected" if selected else "ambiguous"
        logger.debug(f"[PaperOS] search status={status}, candidates={len(candidates)}, selected={len(selected)}")
        return PaperSearchResult(status=status, message="", plan=plan, candidates=candidates, selected=selected)

    async def _resolve_score_dedup(self, plan: SearchPlan) -> list[PaperCandidate]:
        candidates = await self.metadata_resolver.resolve(plan)
        candidates = score_candidates(plan, candidates)
        candidates = self.deduplicator.dedup(candidates)
        candidates = score_candidates(plan, candidates)
        return candidates
