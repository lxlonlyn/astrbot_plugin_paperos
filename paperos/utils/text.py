from __future__ import annotations

import re
import unicodedata

_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "to", "in", "on", "with", "by",
    "is", "are", "was", "were", "be", "being", "been",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s.:-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title: str) -> str:
    text = normalize_text(title)
    words = [w for w in text.split() if w not in _STOPWORDS]
    return " ".join(words)


def token_set(text: str) -> set[str]:
    return {w for w in normalize_text(text).split() if w and w not in _STOPWORDS}


def looks_like_exact_title(text: str) -> bool:
    raw = text.strip()
    if raw.startswith(("《", "\"", "'")) and raw.endswith(("》", "\"", "'")):
        return True
    # Heuristic: a short query with title-like words is likely a title.
    words = normalize_text(raw).split()
    return 4 <= len(words) <= 14 and not raw.endswith("?") and "论文" not in raw and "papers" not in raw.lower()


def strip_title_quotes(text: str) -> str:
    return text.strip().strip("《》\"'“”‘’ ")
