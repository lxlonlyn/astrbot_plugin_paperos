from __future__ import annotations

import re

from ..models import HypothesisKind, PaperHypothesis, SearchIntent, SearchPlan

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
_ARXIV_RE = re.compile(r"\b(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)


def fallback_analyze(raw_query: str) -> SearchPlan:
    q = raw_query.strip()
    hypotheses: list[PaperHypothesis] = []

    for doi in _DOI_RE.findall(q):
        hypotheses.append(PaperHypothesis(kind=HypothesisKind.DOI, confidence=0.95, doi=doi, search_queries=[f'doi:"{doi}"']))

    for arxiv_id in _ARXIV_RE.findall(q):
        hypotheses.append(PaperHypothesis(kind=HypothesisKind.ARXIV, confidence=0.9, arxiv_id=arxiv_id, search_queries=[arxiv_id, f"10.48550/arXiv.{arxiv_id}"]))

    for url in _URL_RE.findall(q):
        hypotheses.append(PaperHypothesis(kind=HypothesisKind.URL, confidence=0.75, url=url, search_queries=[url]))

    if not hypotheses:
        # Chinese or vague topic cues should not be forced into exact title matching.
        is_topic = any(x in q for x in ["相关", "综述", "奠基", "经典", "有哪些", "方向", "领域", "topic", "survey", "related"])
        if is_topic:
            hypotheses.append(PaperHypothesis(kind=HypothesisKind.TOPIC, confidence=0.65, search_queries=[q]))
            intent = SearchIntent.TOPIC_DISCOVERY
            final_limit = 5
        else:
            hypotheses.append(PaperHypothesis(kind=HypothesisKind.FUZZY_TITLE, confidence=0.65, title=q, search_queries=[q, f'"{q}"']))
            intent = SearchIntent.FIND_SPECIFIC
            final_limit = 1
    else:
        intent = SearchIntent.DOWNLOAD_KNOWN if len(hypotheses) == 1 else SearchIntent.FIND_MULTIPLE
        final_limit = len(hypotheses)

    return SearchPlan(
        raw_query=raw_query,
        language="unknown",
        intent=intent,
        hypotheses=hypotheses,
        max_candidates=20 if intent == SearchIntent.TOPIC_DISCOVERY else 10,
        final_limit=final_limit,
        need_fulltext=True,
    )
