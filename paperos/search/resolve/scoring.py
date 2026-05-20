from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from ..models import HypothesisKind, PaperCandidate, SearchIntent, SearchPlan


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def token_set(text: str | None) -> set[str]:
    return set(normalize_text(text).split())


def title_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    return 0.65 * seq + 0.35 * jaccard


def score_candidates(plan: SearchPlan, candidates: list[PaperCandidate]) -> list[PaperCandidate]:
    for cand in candidates:
        cand.score, cand.score_reason = score_candidate(plan, cand)
    return sorted(candidates, key=lambda x: x.score, reverse=True)


def score_candidate(plan: SearchPlan, cand: PaperCandidate) -> tuple[float, str]:
    reasons: list[str] = []
    best = 0.0

    for hyp in plan.hypotheses:
        local = 0.0
        if hyp.doi and cand.doi and hyp.doi.lower() == cand.doi.lower():
            local += 0.95
            reasons.append("DOI exact")
        if hyp.arxiv_id and cand.arxiv_id and hyp.arxiv_id.lower().rstrip("v0123456789") in cand.arxiv_id.lower():
            local += 0.9
            reasons.append("arXiv exact")
        if hyp.title:
            sim = title_similarity(hyp.title, cand.title)
            local += 0.65 * sim
            if sim > 0.75:
                reasons.append(f"title sim {sim:.2f}")
        if hyp.translated_title:
            sim = title_similarity(hyp.translated_title, cand.title)
            local += 0.55 * sim
            if sim > 0.75:
                reasons.append(f"translated title sim {sim:.2f}")
        if hyp.authors and cand.authors:
            ha = {normalize_text(x) for x in hyp.authors}
            ca = {normalize_text(x) for x in cand.authors}
            overlap = len(ha & ca) / max(1, len(ha))
            local += 0.12 * overlap
            if overlap:
                reasons.append("author overlap")
        if hyp.year and cand.year:
            if hyp.year == cand.year:
                local += 0.08
                reasons.append("year match")
            elif abs(hyp.year - cand.year) <= 1:
                local += 0.03
        if hyp.venue and cand.venue:
            sim = title_similarity(hyp.venue, cand.venue)
            local += 0.05 * sim
        if hyp.kind in {HypothesisKind.TOPIC, HypothesisKind.FUZZY_TITLE}:
            for sq in hyp.search_queries[:3]:
                q_tokens = token_set(sq)
                c_tokens = token_set((cand.title or "") + " " + (cand.abstract or ""))
                overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens))
                local += 0.18 * overlap
        local *= max(0.4, hyp.confidence)
        best = max(best, local)

    if plan.intent == SearchIntent.TOPIC_DISCOVERY:
        query_tokens = token_set((plan.translated_query or plan.raw_query) + " " + " ".join(plan.topic_keywords))
        doc_tokens = token_set((cand.title or "") + " " + (cand.abstract or ""))
        overlap = len(query_tokens & doc_tokens) / max(1, len(query_tokens))
        best = max(best, 0.4 * overlap)
        if cand.citation_count:
            best += min(0.18, math.log10(cand.citation_count + 1) / 20)
            reasons.append("citation boost")

    if cand.doi:
        best += 0.04
    if cand.download_url:
        best += 0.03
    if cand.abstract:
        best += 0.02

    return min(best, 1.0), ", ".join(dict.fromkeys(reasons)) or "metadata relevance"
