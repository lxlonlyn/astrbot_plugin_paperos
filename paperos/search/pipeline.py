from astrbot.api import logger

from ..config import PaperOSConfig
from .acquire.fulltext_resolver import FulltextResolver
from .acquire.verifier import FulltextVerifier
from .models import FulltextStatus, PaperCandidate, PaperSearchResult, SearchPlan
from .query.analyzer import AstrBotLLMQueryAnalyzer
from .resolve.candidate_resolver import CandidateResolver
from .resolve.dedup import PaperDeduplicator
from .resolve.disambiguator import PaperDisambiguator
from .resolve.scoring import score_candidates


class PaperSearchPipeline:
    """Stage-by-stage orchestration for PaperOS search."""

    def __init__(
        self,
        *,
        cfg: PaperOSConfig,
        query_analyzer: AstrBotLLMQueryAnalyzer,
        metadata_resolver: CandidateResolver,
        deduplicator: PaperDeduplicator,
        disambiguator: PaperDisambiguator,
        fulltext_resolver: FulltextResolver,
        verifier: FulltextVerifier,
    ):
        self.cfg = cfg
        self.query_analyzer = query_analyzer
        self.metadata_resolver = metadata_resolver
        self.deduplicator = deduplicator
        self.disambiguator = disambiguator
        self.fulltext_resolver = fulltext_resolver
        self.verifier = verifier

    async def run(self, raw_query: str, *, event=None, need_fulltext: bool = True) -> PaperSearchResult:
        if not self.cfg.core_api.enabled:
            logger.debug("[PaperOS][Pipeline] aborted: CORE API disabled")
            return PaperSearchResult(status="disabled", message="CORE API disabled")

        logger.debug("[PaperOS][Pipeline] start raw_query=%r need_fulltext=%s", raw_query, need_fulltext)

        plan = await self.query_analyzer.analyze(raw_query, event=event)
        llm_need_fulltext = plan.need_fulltext
        plan.need_fulltext = bool(need_fulltext)

        logger.debug(
            "[PaperOS][Pipeline] fulltext_policy caller=%s llm=%s final=%s",
            need_fulltext,
            llm_need_fulltext,
            plan.need_fulltext,
        )
        logger.debug("[PaperOS][Pipeline] stage=query_analyze %s", self._summarize_plan(plan))

        candidates = await self._resolve_score_dedup(plan)
        logger.debug("[PaperOS][Pipeline] stage=metadata_resolve %s", self._summarize_candidates(candidates))

        repair_rounds = max(0, self.cfg.query_analyzer.max_repair_rounds)
        for round_idx in range(repair_rounds):
            if candidates:
                break
            logger.debug("[PaperOS][Pipeline] stage=repair round=%d reason=no candidates", round_idx + 1)
            plan = await self.query_analyzer.repair(
                raw_query,
                previous_plan=plan,
                failure_reason="metadata providers returned zero candidates",
                event=event,
            )
            logger.debug("[PaperOS][Pipeline] stage=query_repair %s", self._summarize_plan(plan))
            candidates = await self._resolve_score_dedup(plan)
            logger.debug("[PaperOS][Pipeline] stage=metadata_resolve_after_repair %s", self._summarize_candidates(candidates))

        if not candidates:
            return PaperSearchResult(
                status="not_found",
                message="metadata providers returned zero candidates",
                plan=plan,
            )

        selected = self.disambiguator.select(plan, candidates)
        logger.debug("[PaperOS][Pipeline] stage=disambiguate selected=%s", self._summarize_candidates(selected))

        targets: list[PaperCandidate] = selected or candidates[: plan.final_limit]

        if plan.need_fulltext:
            await self._resolve_fulltext(targets)

            if not self._has_verified_pdf(targets):
                logger.debug(
                    "[PaperOS][Pipeline] done status=not_found reason=no_verified_pdf targets=%d",
                    len(targets),
                )
                return PaperSearchResult(
                    status="not_found",
                    message="found metadata candidates, but no verified PDF was downloaded",
                    plan=plan,
                    candidates=candidates,
                    selected=[],
                )

        status = "selected" if selected else "ambiguous"
        logger.debug(
            "[PaperOS][Pipeline] done status=%s candidates=%d selected=%d fulltext=%s",
            status,
            len(candidates),
            len(selected),
            plan.need_fulltext,
        )

        return PaperSearchResult(
            status=status,
            message="",
            plan=plan,
            candidates=candidates,
            selected=selected,
        )

    async def _resolve_score_dedup(self, plan: SearchPlan) -> list[PaperCandidate]:
        candidates = await self.metadata_resolver.resolve(plan)
        scored = score_candidates(plan, candidates)
        deduped = self.deduplicator.dedup(scored)
        return score_candidates(plan, deduped)

    async def _resolve_fulltext(self, papers: list[PaperCandidate]) -> None:
        for paper in papers:
            locations = await self.fulltext_resolver.resolve(paper)
            logger.debug(
                "[PaperOS][Pipeline] stage=fulltext_resolve paper=%s locations=%d",
                self._short(paper.title),
                len(locations),
            )

            verified = []
            for loc in locations[: self.cfg.search_policy.max_fulltext_candidates]:
                verified_loc = await self.verifier.verify(loc, paper)
                verified.append(verified_loc)

                if verified_loc.status == FulltextStatus.VERIFIED_PDF:
                    break

            paper.fulltext_locations = verified
            logger.debug(
                "[PaperOS][Pipeline] stage=fulltext_verify paper=%s statuses=%s pdf=%s",
                self._short(paper.title),
                [loc.status.value for loc in verified],
                bool(paper.best_verified_pdf()),
            )

    def _has_verified_pdf(self, papers: list[PaperCandidate]) -> bool:
        return any(paper.best_verified_pdf() is not None for paper in papers)

    def _summarize_plan(self, plan: SearchPlan) -> str:
        kinds = [h.kind.value for h in plan.hypotheses[:5]]
        sample_queries: list[str] = []
        for hyp in plan.hypotheses[:3]:
            sample_queries.extend(hyp.search_queries[:2])
        sample_queries = [self._short(q, 60) for q in sample_queries[:4]]
        return (
            f"intent={plan.intent.value}, lang={plan.language}, hypotheses={len(plan.hypotheses)} {kinds}, "
            f"max_candidates={plan.max_candidates}, final_limit={plan.final_limit}, "
            f"need_fulltext={plan.need_fulltext}, queries={sample_queries}"
        )

    def _summarize_candidates(self, candidates: list[PaperCandidate], *, limit: int = 3) -> str:
        if not candidates:
            return "count=0"
        items = []
        for cand in candidates[:limit]:
            items.append(
                f"{self._short(cand.title, 55)}|year={cand.year or '?'}|score={cand.score:.2f}|src={cand.source}"
            )
        suffix = "" if len(candidates) <= limit else f" ... +{len(candidates) - limit}"
        return f"count={len(candidates)} sample=[" + "; ".join(items) + "]" + suffix

    def _short(self, text: str, limit: int = 70) -> str:
        return text if len(text) <= limit else text[: limit - 3] + "..."

    async def aclose(self) -> None:
        await self.metadata_resolver.aclose()
        await self.fulltext_resolver.aclose()
        await self.verifier.aclose()
