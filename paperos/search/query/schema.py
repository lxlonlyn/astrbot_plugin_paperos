from __future__ import annotations

from typing import Any

from ..models import HypothesisKind, PaperHypothesis, SearchIntent, SearchPlan


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_search_plan(data: dict[str, Any], *, raw_query: str, max_hypotheses: int = 5) -> SearchPlan:
    intent_raw = str(data.get("intent") or "find_specific").strip().lower()
    try:
        intent = SearchIntent(intent_raw)
    except ValueError:
        intent = SearchIntent.FIND_SPECIFIC

    hypotheses: list[PaperHypothesis] = []
    raw_hyps = data.get("hypotheses") or []
    if not isinstance(raw_hyps, list):
        raw_hyps = []

    for item in raw_hyps[:max_hypotheses]:
        if not isinstance(item, dict):
            continue
        kind_raw = str(item.get("kind") or "fuzzy_title").strip().lower()
        try:
            kind = HypothesisKind(kind_raw)
        except ValueError:
            kind = HypothesisKind.FUZZY_TITLE

        hypotheses.append(
            PaperHypothesis(
                kind=kind,
                confidence=_safe_float(item.get("confidence"), 0.5),
                title=(str(item.get("title")).strip() if item.get("title") else None),
                translated_title=(str(item.get("translated_title")).strip() if item.get("translated_title") else None),
                doi=(str(item.get("doi")).strip() if item.get("doi") else None),
                arxiv_id=(str(item.get("arxiv_id")).strip() if item.get("arxiv_id") else None),
                url=(str(item.get("url")).strip() if item.get("url") else None),
                authors=_as_str_list(item.get("authors")),
                year=_safe_int(item.get("year")),
                venue=(str(item.get("venue")).strip() if item.get("venue") else None),
                search_queries=_as_str_list(item.get("search_queries")),
                note=(str(item.get("note")).strip() if item.get("note") else None),
            )
        )

    max_candidates = _safe_int(data.get("max_candidates")) or 20
    final_limit = _safe_int(data.get("final_limit")) or 5

    return SearchPlan(
        raw_query=raw_query,
        language=str(data.get("language") or "unknown"),
        intent=intent,
        hypotheses=hypotheses,
        topic_keywords=_as_str_list(data.get("topic_keywords")),
        translated_query=(str(data.get("translated_query")).strip() if data.get("translated_query") else None),
        max_candidates=max(1, min(max_candidates, 50)),
        final_limit=max(1, min(final_limit, 20)),
        need_fulltext=bool(data.get("need_fulltext", True)),
        allow_topic_expansion=bool(data.get("allow_topic_expansion", False)),
        raw_llm_output=data,
    )
