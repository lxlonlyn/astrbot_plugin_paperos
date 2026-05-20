from __future__ import annotations

import re

from ...models import HypothesisKind, PaperHypothesis, SearchIntent, SearchPlan


def quote(value: str) -> str:
    return '"' + value.replace('"', " ").strip() + '"'


def build_core_queries_for_hypothesis(hyp: PaperHypothesis, plan: SearchPlan) -> list[str]:
    queries: list[str] = []

    if hyp.doi:
        queries.append(f"doi:{quote(hyp.doi)}")
        queries.append(quote(hyp.doi))

    if hyp.arxiv_id:
        queries.append(f"arxivId:{quote(hyp.arxiv_id)}")
        queries.append(f"doi:{quote('10.48550/arXiv.' + hyp.arxiv_id)}")
        queries.append(hyp.arxiv_id)

    if hyp.title:
        queries.append(f"title:{quote(hyp.title)}")
        queries.append(quote(hyp.title))
        title_tokens = _important_tokens(hyp.title)
        if 2 <= len(title_tokens) <= 8:
            queries.append(" AND ".join(f"title:{quote(t)}" for t in title_tokens))

    if hyp.translated_title and hyp.translated_title != hyp.title:
        queries.append(f"title:{quote(hyp.translated_title)}")
        queries.append(quote(hyp.translated_title))

    for sq in hyp.search_queries:
        queries.append(sq)

    if hyp.kind == HypothesisKind.TOPIC or plan.intent == SearchIntent.TOPIC_DISCOVERY:
        for kw in plan.topic_keywords:
            queries.append(f"title:{quote(kw)} OR abstract:{quote(kw)}")
        if plan.translated_query:
            queries.append(f"title:{quote(plan.translated_query)} OR abstract:{quote(plan.translated_query)}")
            queries.append(plan.translated_query)

    if hyp.url:
        # CORE usually does not search arbitrary URLs well, but keep it as a last-resort clue.
        queries.append(hyp.url)

    return _dedup_keep_order([q.strip() for q in queries if q and q.strip()])


def build_core_queries(plan: SearchPlan) -> list[str]:
    queries: list[str] = []
    for hyp in plan.hypotheses:
        queries.extend(build_core_queries_for_hypothesis(hyp, plan))
    if not queries:
        queries.append(plan.translated_query or plan.raw_query)
    return _dedup_keep_order(queries)


def _important_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]+", text.lower())
    stop = {"the", "a", "an", "is", "are", "of", "for", "to", "in", "on", "and", "or", "with"}
    return [t for t in tokens if t not in stop]


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
