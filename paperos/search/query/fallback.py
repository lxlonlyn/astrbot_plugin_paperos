from __future__ import annotations

import re

from ..models import HypothesisKind, PaperHypothesis, SearchContext, SearchIntent, SearchPlan

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
_ARXIV_RE = re.compile(r"\b(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b", re.I)
_OLD_ARXIV_RE = re.compile(r"\b([a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def fallback_analyze(raw_query: str, context: SearchContext | None = None) -> SearchPlan:
    q = raw_query.strip()
    has_cjk = contains_cjk(q)
    hypotheses: list[PaperHypothesis] = []
    hint_queries = _clean_list((context.expanded_queries if context else []) + (context.preferred_concepts if context else []))
    known_titles = _clean_list(context.known_titles if context else [])

    identifier_text = " ".join([q] + _clean_list(context.known_identifiers if context else []))

    for doi in _DOI_RE.findall(identifier_text):
        hypotheses.append(
            PaperHypothesis(
                kind=HypothesisKind.DOI,
                confidence=0.95,
                doi=doi,
                search_queries=[f'"{doi}" pdf', f'"{doi}" paper'],
            )
        )

    for arxiv_id in _ARXIV_RE.findall(identifier_text) + _OLD_ARXIV_RE.findall(identifier_text):
        hypotheses.append(
            PaperHypothesis(
                kind=HypothesisKind.ARXIV,
                confidence=0.9,
                arxiv_id=arxiv_id,
                search_queries=[f"arxiv {arxiv_id}", f"{arxiv_id} pdf"],
            )
        )

    for url in _URL_RE.findall(identifier_text):
        hypotheses.append(PaperHypothesis(kind=HypothesisKind.URL, confidence=0.8, url=url, search_queries=[url]))

    for title in known_titles:
        title_queries = [f'"{title}"', f'"{title}" pdf', f'"{title}" arxiv']
        hypotheses.append(
            PaperHypothesis(
                kind=HypothesisKind.TITLE,
                confidence=0.75,
                title=title,
                translated_title=title,
                search_queries=title_queries + hint_queries[:2],
                note="workflow-provided title hint",
            )
        )

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
            search_queries = hint_queries if has_cjk else [q, f'"{q}" pdf', f'"{q}" arxiv'] + hint_queries
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


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = re.sub(r"\s+", " ", str(value or "").strip())
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned
