from __future__ import annotations

from .identifiers import extract_arxiv_id, extract_core_id, extract_doi, looks_like_url
from .models import PaperQuery, QueryKind
from ..utils.text import looks_like_exact_title, strip_title_quotes

_TOPIC_HINTS = (
    "奠基", "综述", "相关工作", "代表", "经典", "方向", "领域", "话题", "topic",
    "survey", "foundational", "seminal", "representative", "classic", "papers about",
)


def classify_query(raw_query: str) -> PaperQuery:
    raw = (raw_query or "").strip()
    doi = extract_doi(raw)
    arxiv_id = extract_arxiv_id(raw)
    core_id = extract_core_id(raw)

    if doi or arxiv_id or core_id or looks_like_url(raw):
        return PaperQuery(raw=raw, kind=QueryKind.IDENTIFIER, doi=doi, arxiv_id=arxiv_id, core_id=core_id)

    lower = raw.lower()
    if any(h in lower for h in _TOPIC_HINTS):
        return PaperQuery(raw=raw, kind=QueryKind.TOPIC, topic=raw)

    title = strip_title_quotes(raw)
    if looks_like_exact_title(raw):
        return PaperQuery(raw=raw, kind=QueryKind.EXACT_TITLE, title=title)

    # Short, incomplete strings like "you need attention" go here.
    return PaperQuery(raw=raw, kind=QueryKind.FUZZY_TITLE, title=title)
