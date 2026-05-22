from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = _NON_WORD_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value


def normalize_identifier(scheme: str, value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if scheme.lower() == "doi":
        value = value.lower()
        value = value.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
        return value.strip()
    if scheme.lower() == "arxiv":
        value = value.lower().removeprefix("arxiv:")
        return value.strip()
    return value.strip()
