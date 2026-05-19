from __future__ import annotations

import re
from urllib.parse import unquote

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_CORE_WORK_RE = re.compile(r"core\.ac\.uk/(?:works|download)/(\d+)", re.IGNORECASE)


def extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(unquote(text or ""))
    if not m:
        return None
    return m.group(0).rstrip(".,;)\]").lower()


def extract_arxiv_id(text: str) -> str | None:
    m = _ARXIV_RE.search(text or "")
    if not m:
        return None
    return m.group(1)


def extract_core_id(text: str) -> str | None:
    m = _CORE_WORK_RE.search(text or "")
    if not m:
        return None
    return m.group(1)


def looks_like_url(text: str) -> bool:
    return (text or "").strip().lower().startswith(("http://", "https://"))
