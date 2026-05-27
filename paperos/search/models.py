from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SearchIntent(str, Enum):
    FIND_SPECIFIC = "find_specific"
    FIND_MULTIPLE = "find_multiple"
    TOPIC_DISCOVERY = "topic_discovery"
    EXPAND_RELATED = "expand_related"
    DOWNLOAD_KNOWN = "download_known"


class HypothesisKind(str, Enum):
    DOI = "doi"
    ARXIV = "arxiv"
    URL = "url"
    TITLE = "title"
    FUZZY_TITLE = "fuzzy_title"
    TOPIC = "topic"
    AUTHOR_VENUE_YEAR = "author_venue_year"


class FulltextStatus(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED_PDF = "verified_pdf"
    HTML_FULLTEXT = "html_fulltext"
    LANDING_ONLY = "landing_only"
    REQUIRES_AUTH = "requires_auth"
    NO_OPEN_ACCESS = "no_open_access"
    INVALID = "invalid"
    FAILED = "failed"


@dataclass
class PaperHypothesis:
    kind: HypothesisKind
    confidence: float = 0.5
    title: str | None = None
    translated_title: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    search_queries: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class SearchPlan:
    raw_query: str
    language: str = "unknown"
    intent: SearchIntent = SearchIntent.FIND_SPECIFIC
    hypotheses: list[PaperHypothesis] = field(default_factory=list)
    topic_keywords: list[str] = field(default_factory=list)
    translated_query: str | None = None
    max_candidates: int = 20
    final_limit: int = 5
    need_fulltext: bool = True
    allow_topic_expansion: bool = False
    raw_llm_output: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebSearchResult:
    """A raw web-search page candidate.

    This is intentionally weaker than PaperCandidate. It is only a page that the
    targeted crawler may inspect; it is not yet a paper metadata record.
    """

    url: str
    title: str = ""
    snippet: str = ""
    source: str = "web"
    rank: int = 0
    query: str = ""


@dataclass
class FulltextLocation:
    """A fulltext acquisition candidate and, after verifier runs, local artifact metadata.

    Only status == VERIFIED_PDF means a local PDF has been downloaded and
    validated. URL candidates from web pages are never trusted until verifier
    checks content-type, magic bytes and page count.
    """

    url: str
    source: str
    kind: str = "pdf"  # pdf/html/landing
    status: FulltextStatus = FulltextStatus.CANDIDATE
    license: str | None = None
    version: str | None = None
    host_type: str | None = None
    confidence: float = 0.0
    reason: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    local_path: str | None = None
    final_url: str | None = None
    filename: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    page_count: int | None = None


@dataclass
class PaperCandidate:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    core_id: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    citation_count: int | None = None
    download_url: str | None = None
    landing_url: str | None = None
    fulltext_locations: list[FulltextLocation] = field(default_factory=list)
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    score_reason: str = ""

    def best_verified_pdf(self) -> FulltextLocation | None:
        for loc in self.fulltext_locations:
            if loc.status == FulltextStatus.VERIFIED_PDF and loc.local_path:
                return loc
        return None


@dataclass
class PaperSearchResult:
    status: str
    message: str = ""
    plan: SearchPlan | None = None
    candidates: list[PaperCandidate] = field(default_factory=list)
    selected: list[PaperCandidate] = field(default_factory=list)
