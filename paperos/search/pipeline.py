from __future__ import annotations

from astrbot.api import logger

from ..config import PaperOSConfig
from .acquire.verifier import FulltextVerifier
from .crawl.targeted import TargetedPaperCrawler
from .models import FulltextStatus, PaperCandidate, PaperSearchResult, SearchContext, SearchPlan
from .query.analyzer import AstrBotLLMQueryAnalyzer
from .resolve.dedup import PaperDeduplicator
from .resolve.disambiguator import PaperDisambiguator
from .resolve.scoring import title_similarity, score_candidates


class PaperSearchPipeline:
    """Orchestrates LLM source proposal -> targeted crawl -> PDF verification."""

    def __init__(
        self,
        *,
        cfg: PaperOSConfig,
        query_analyzer: AstrBotLLMQueryAnalyzer,
        crawler: TargetedPaperCrawler,
        deduplicator: PaperDeduplicator,
        disambiguator: PaperDisambiguator,
        verifier: FulltextVerifier,
    ):
        self.cfg = cfg
        self.query_analyzer = query_analyzer
        self.crawler = crawler
        self.deduplicator = deduplicator
        self.disambiguator = disambiguator
        self.verifier = verifier

    async def run(
        self,
        raw_query: str,
        *,
        event=None,
        need_fulltext: bool = True,
        context: SearchContext | None = None,
    ) -> PaperSearchResult:
        if not self.cfg.crawler.enabled:
            logger.debug("[PaperOS][Pipeline] aborted: crawler disabled")
            return PaperSearchResult(status="disabled", message="crawler disabled")

        logger.debug("[PaperOS][Pipeline] start raw_query=%r need_fulltext=%s", raw_query, need_fulltext)
        plan = await self.query_analyzer.analyze(raw_query, event=event, context=context)
        llm_need_fulltext = plan.need_fulltext
        plan.need_fulltext = bool(need_fulltext)
        logger.debug(
            "[PaperOS][Pipeline] stage=query_analyze %s fulltext_policy caller=%s llm=%s final=%s",
            self._summarize_plan(plan),
            need_fulltext,
            llm_need_fulltext,
            plan.need_fulltext,
        )

        candidates = await self._discover_score_dedup(plan)
        logger.debug("[PaperOS][Pipeline] stage=discover %s", self._summarize_candidates(candidates))

        repair_rounds = max(0, self.cfg.query_analyzer.max_repair_rounds)
        for round_idx in range(repair_rounds):
            if candidates:
                break
            logger.debug("[PaperOS][Pipeline] stage=repair round=%d reason=no concrete sources", round_idx + 1)
            plan = await self.query_analyzer.repair(
                raw_query,
                previous_plan=plan,
                failure_reason=(
                    "The crawler found no concrete source. Provide arXiv IDs, DOI, "
                    "OpenReview/ACL/CVF/PMLR/arXiv URLs, or direct PDF URLs if you know them."
                ),
                event=event,
                context=context,
            )
            candidates = await self._discover_score_dedup(plan)
            logger.debug(
                "[PaperOS][Pipeline] stage=discover_after_repair %s",
                self._summarize_candidates(candidates),
            )

        if not candidates:
            return PaperSearchResult(
                status="not_found",
                message=(
                    "LLM did not produce usable concrete paper sources. "
                    "This stage has no generic web-search backend; provide a URL/arXiv ID/DOI, "
                    "or use a model/provider that can propose such sources."
                ),
                plan=plan,
            )

        selected = self.disambiguator.select(plan, candidates)
        targets: list[PaperCandidate] = selected or candidates[: plan.final_limit]
        logger.debug("[PaperOS][Pipeline] stage=disambiguate selected=%s", self._summarize_candidates(selected))

        if plan.need_fulltext:
            await self._verify_fulltext(targets)
            if not self._has_verified_pdf(targets):
                logger.debug(
                    "[PaperOS][Pipeline] done status=not_found reason=no_verified_pdf targets=%d",
                    len(targets),
                )
                return PaperSearchResult(
                    status="not_found",
                    message="found concrete paper candidates, but no candidate URL was verified as PDF",
                    plan=plan,
                    candidates=candidates,
                    selected=selected,
                )

        status = "selected" if selected else "ambiguous"
        logger.debug(
            "[PaperOS][Pipeline] done status=%s candidates=%d selected=%d fulltext=%s",
            status,
            len(candidates),
            len(selected),
            plan.need_fulltext,
        )
        return PaperSearchResult(status=status, message="", plan=plan, candidates=candidates, selected=selected)

    async def _discover_score_dedup(self, plan: SearchPlan) -> list[PaperCandidate]:
        candidates = await self.crawler.discover(plan)
        candidates = self._filter_bad_identifier_candidates(plan, candidates)
        scored = score_candidates(plan, candidates)
        deduped = self.deduplicator.dedup(scored)
        logger.debug(
            "[PaperOS][Pipeline] stage=dedup before=%d after=%d",
            len(scored),
            len(deduped),
        )
        return score_candidates(plan, deduped)

    def _filter_bad_identifier_candidates(
        self,
        plan: SearchPlan,
        candidates: list[PaperCandidate],
    ) -> list[PaperCandidate]:
        filtered: list[PaperCandidate] = []
        for cand in candidates:
            bad_reason = self._bad_identifier_reason(plan, cand)
            if bad_reason:
                cand.raw["paperos_rejected_reason"] = bad_reason
                logger.debug(
                    "[PaperOS][Pipeline] reject_identifier_candidate source=%s title=%s reason=%s",
                    cand.source,
                    self._short(cand.title),
                    bad_reason,
                )
                continue
            filtered.append(cand)
        return filtered

    def _bad_identifier_reason(self, plan: SearchPlan, cand: PaperCandidate) -> str | None:
        for hyp in plan.hypotheses:
            expected_title = hyp.translated_title or hyp.title
            if not expected_title:
                continue

            id_matches = False
            if hyp.arxiv_id and cand.arxiv_id and hyp.arxiv_id.lower().rstrip("v0123456789") in cand.arxiv_id.lower():
                id_matches = True
            if hyp.doi and cand.doi and hyp.doi.lower() == cand.doi.lower():
                id_matches = True
            if hyp.url and cand.landing_url and hyp.url.rstrip("/") == cand.landing_url.rstrip("/"):
                id_matches = True

            if not id_matches:
                continue

            sim = title_similarity(expected_title, cand.title)
            if sim < self.cfg.search_policy.identifier_title_min_similarity:
                return (
                    f"identifier matched but fetched title disagrees "
                    f"similarity={sim:.2f} threshold={self.cfg.search_policy.identifier_title_min_similarity:.2f}"
                )
        return None

    async def _verify_fulltext(self, papers: list[PaperCandidate]) -> None:
        for paper in papers:
            candidates = paper.fulltext_locations[: self.cfg.search_policy.max_fulltext_candidates]
            logger.debug(
                "[PaperOS][Pipeline] stage=fulltext_verify_start paper=%s candidates=%d",
                self._short(paper.title),
                len(candidates),
            )
            verified = []
            for loc in candidates:
                verified_loc = await self.verifier.verify(loc, paper)
                verified.append(verified_loc)
                if verified_loc.status == FulltextStatus.VERIFIED_PDF:
                    break
            paper.fulltext_locations = verified + [loc for loc in paper.fulltext_locations if loc not in candidates]
            logger.debug(
                "[PaperOS][Pipeline] stage=fulltext_verify_done paper=%s statuses=%s pdf=%s",
                self._short(paper.title),
                [loc.status.value for loc in verified],
                bool(paper.best_verified_pdf()),
            )

    def _has_verified_pdf(self, papers: list[PaperCandidate]) -> bool:
        return any(paper.best_verified_pdf() is not None for paper in papers)

    def _summarize_plan(self, plan: SearchPlan) -> str:
        kinds = [h.kind.value for h in plan.hypotheses[:5]]
        direct = 0
        for hyp in plan.hypotheses:
            direct += int(bool(hyp.url)) + int(bool(hyp.arxiv_id)) + int(bool(hyp.doi))
        return (
            f"intent={plan.intent.value}, lang={plan.language}, hypotheses={len(plan.hypotheses)} {kinds}, "
            f"direct_sources={direct}, max_candidates={plan.max_candidates}, "
            f"final_limit={plan.final_limit}, need_fulltext={plan.need_fulltext}"
        )

    def _summarize_candidates(self, candidates: list[PaperCandidate], *, limit: int = 3) -> str:
        if not candidates:
            return "count=0"
        items = []
        for cand in candidates[:limit]:
            items.append(
                f"{self._short(cand.title, 55)}|year={cand.year or '?'}|score={cand.score:.2f}|src={cand.source}|pdfs={len(cand.fulltext_locations)}"
            )
        suffix = "" if len(candidates) <= limit else f" ... +{len(candidates) - limit}"
        return f"count={len(candidates)} sample=[" + "; ".join(items) + "]" + suffix

    def _short(self, text: str, limit: int = 70) -> str:
        return text if len(text) <= limit else text[: limit - 3] + "..."

    async def aclose(self) -> None:
        await self.crawler.aclose()
        await self.verifier.aclose()
