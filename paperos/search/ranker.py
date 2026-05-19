from __future__ import annotations

from difflib import SequenceMatcher
from math import log10

from .models import PaperCandidate, PaperQuery, QueryKind
from ..utils.text import normalize_title, token_set


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _citation_score(count: int | None) -> float:
    if not count or count <= 0:
        return 0.0
    return min(1.0, log10(count + 1) / 5.0)


def score_candidate(query: PaperQuery, cand: PaperCandidate) -> PaperCandidate:
    title_norm = normalize_title(cand.title)
    query_text = query.title or query.topic or query.raw
    query_norm = normalize_title(query_text)

    if query.kind == QueryKind.IDENTIFIER:
        if query.doi and cand.doi and query.doi.lower() == cand.doi.lower():
            cand.score = 1.0
            cand.score_reason = "DOI exact match"
            return cand
        if query.arxiv_id and cand.arxiv_id and query.arxiv_id.lower() == cand.arxiv_id.lower():
            cand.score = 1.0
            cand.score_reason = "arXiv exact match"
            return cand
        if query.core_id and cand.core_id and query.core_id == cand.core_id:
            cand.score = 1.0
            cand.score_reason = "CORE id exact match"
            return cand
        cand.score = max(_ratio(query_norm, title_norm), 0.4 if cand.doi or cand.arxiv_id else 0.0)
        cand.score_reason = "identifier fallback"
        return cand

    if query.kind in (QueryKind.EXACT_TITLE, QueryKind.FUZZY_TITLE):
        title_ratio = _ratio(query_norm, title_norm)
        title_jaccard = _jaccard(token_set(query_norm), token_set(title_norm))
        id_bonus = 0.05 if cand.doi or cand.arxiv_id else 0.0
        cite_bonus = 0.05 * _citation_score(cand.citation_count)
        cand.score = min(1.0, 0.65 * title_ratio + 0.25 * title_jaccard + id_bonus + cite_bonus)
        cand.score_reason = f"title_ratio={title_ratio:.2f}, token_overlap={title_jaccard:.2f}"
        return cand

    # Topic discovery: do not over-trust title similarity. Prefer topic overlap + impact.
    text = " ".join([cand.title or "", cand.abstract or ""])
    overlap = _jaccard(token_set(query_norm), token_set(text))
    cite = _citation_score(cand.citation_count)
    availability = 1.0 if cand.download_url else 0.0
    cand.score = min(1.0, 0.60 * overlap + 0.25 * cite + 0.15 * availability)
    cand.score_reason = f"topic_overlap={overlap:.2f}, citation={cite:.2f}, pdf={availability:.0f}"
    return cand


def rank_candidates(query: PaperQuery, candidates: list[PaperCandidate]) -> list[PaperCandidate]:
    dedup: dict[str, PaperCandidate] = {}
    for c in candidates:
        if not c.title:
            continue
        scored = score_candidate(query, c)
        key = scored.identity_key()
        old = dedup.get(key)
        if old is None or scored.score > old.score:
            dedup[key] = scored
    return sorted(dedup.values(), key=lambda c: c.score, reverse=True)
