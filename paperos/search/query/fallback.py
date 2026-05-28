from __future__ import annotations

import re

from ..models import HypothesisKind, PaperHypothesis, SearchIntent, SearchPlan

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
_ARXIV_RE = re.compile(r"\b(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b", re.I)
_OLD_ARXIV_RE = re.compile(r"\b([a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def fallback_analyze(raw_query: str) -> SearchPlan:
    q = raw_query.strip()
    has_cjk = contains_cjk(q)
    hypotheses: list[PaperHypothesis] = []

    for doi in _DOI_RE.findall(q):
        hypotheses.append(
            PaperHypothesis(
                kind=HypothesisKind.DOI,
                confidence=0.95,
                doi=doi,
                search_queries=[f'"{doi}" pdf', f'"{doi}" paper'],
            )
        )

    for arxiv_id in _ARXIV_RE.findall(q) + _OLD_ARXIV_RE.findall(q):
        hypotheses.append(
            PaperHypothesis(
                kind=HypothesisKind.ARXIV,
                confidence=0.9,
                arxiv_id=arxiv_id,
                search_queries=[f"arxiv {arxiv_id}", f"{arxiv_id} pdf"],
            )
        )

    for url in _URL_RE.findall(q):
        hypotheses.append(PaperHypothesis(kind=HypothesisKind.URL, confidence=0.8, url=url, search_queries=[url]))

    if not hypotheses:
        is_topic = any(
            x in q
            for x in ["相关", "综述", "奠基", "经典", "有哪些", "方向", "领域", "topic", "survey", "related", "foundational"]
        )
        if is_topic:
            search_queries = []
            if not has_cjk:
                search_queries = [
                    f"{q} foundational paper pdf",
                    f"{q} important papers arxiv",
                    f"{q} survey representative papers",
                ]
            hypotheses.append(
                PaperHypothesis(
                    kind=HypothesisKind.TOPIC,
                    confidence=0.65,
                    title=None if has_cjk else q,
                    search_queries=search_queries,
                    note=(
                        "fallback analyzer detected non-English input; LLM translation is required for useful title lookup"
                        if has_cjk
                        else None
                    ),
                )
            )
            intent = SearchIntent.TOPIC_DISCOVERY
            final_limit = 5
        else:
            search_queries = [] if has_cjk else [q, f'"{q}" pdf', f'"{q}" arxiv']
            hypotheses.append(
                PaperHypothesis(
                    kind=HypothesisKind.FUZZY_TITLE,
                    confidence=0.65,
                    title=None if has_cjk else q,
                    search_queries=search_queries,
                    note=(
                        "fallback analyzer detected non-English input; LLM translation is required for useful title lookup"
                        if has_cjk
                        else None
                    ),
                )
            )
            intent = SearchIntent.FIND_SPECIFIC
            final_limit = 1
    else:
        intent = SearchIntent.DOWNLOAD_KNOWN if len(hypotheses) == 1 else SearchIntent.FIND_MULTIPLE
        final_limit = len(hypotheses)

    return SearchPlan(
        raw_query=raw_query,
        language="zh" if has_cjk else "unknown",
        intent=intent,
        hypotheses=hypotheses,
        max_candidates=20 if intent == SearchIntent.TOPIC_DISCOVERY else 10,
        final_limit=final_limit,
        need_fulltext=True,
    )
