from __future__ import annotations

from .models import PaperQuery, QueryKind
from ..utils.text import normalize_text, strip_title_quotes


def _quote(value: str) -> str:
    value = (value or "").replace('"', " ").strip()
    return f'"{value}"'


def build_core_queries(query: PaperQuery, *, enable_rewrite: bool = True) -> list[str]:
    """Build a small ordered list of CORE query-language strings.

    The goal is not exhaustive recall. We keep the list small to avoid API cost
    and only broaden when the earlier query is likely too strict.
    """
    if query.kind == QueryKind.IDENTIFIER:
        out: list[str] = []
        if query.doi:
            out.append(f"doi:{_quote(query.doi)}")
        if query.arxiv_id:
            out.append(f"arxivId:{_quote(query.arxiv_id)}")
            out.append(f"doi:{_quote('10.48550/arXiv.' + query.arxiv_id)}")
        if query.core_id:
            out.append(f"id:{query.core_id}")
        # URL without resolvable identifier cannot be handled well by CORE alone.
        return out or [query.raw]

    if query.kind == QueryKind.EXACT_TITLE:
        title = strip_title_quotes(query.title or query.raw)
        return [f"title:{_quote(title)}", _quote(title)] if enable_rewrite else [f"title:{_quote(title)}"]

    if query.kind == QueryKind.FUZZY_TITLE:
        title = strip_title_quotes(query.title or query.raw)
        tokens = normalize_text(title).split()
        # Require important words in title when possible; fallback to general query.
        if len(tokens) >= 2:
            and_query = " AND ".join(f"title:{_quote(t)}" for t in tokens)
            return [and_query, f"title:{_quote(title)}", title]
        return [title]

    # Topic: search title/abstract first, then broad query. Keep limit modest.
    topic = query.topic or query.raw
    topic_norm = strip_title_quotes(topic)
    return [
        f"title:{_quote(topic_norm)} OR abstract:{_quote(topic_norm)}",
        topic_norm,
    ]
