from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class QueryKind(str, Enum):
    IDENTIFIER = "identifier"  # DOI / arXiv ID / CORE ID / URL containing ID
    EXACT_TITLE = "exact_title"
    FUZZY_TITLE = "fuzzy_title"
    TOPIC = "topic"


@dataclass(frozen=True)
class PaperQuery:
    raw: str
    kind: QueryKind
    doi: str | None = None
    arxiv_id: str | None = None
    core_id: str | None = None
    title: str | None = None
    topic: str | None = None


@dataclass
class PaperCandidate:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    core_id: str | None = None
    download_url: str | None = None
    landing_url: str | None = None
    citation_count: int | None = None
    source: str = "core"
    raw: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    score_reason: str = ""

    def identity_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower()}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id.lower()}"
        if self.core_id:
            return f"core:{self.core_id}"
        return "title:" + " ".join(self.title.lower().split())


@dataclass
class PaperSearchResult:
    query: PaperQuery
    candidates: list[PaperCandidate]
    accepted: PaperCandidate | None = None
    ambiguous: bool = False
    status: Literal["ok", "not_found", "disabled", "error"] = "ok"
    message: str = ""

    def best(self) -> PaperCandidate | None:
        return self.accepted or (self.candidates[0] if self.candidates else None)
