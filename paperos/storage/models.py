from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FulltextLocationRecord:
    url: str
    source: str = "unknown"
    kind: str = "pdf"
    status: str = "candidate"
    license: str | None = None
    version: str | None = None
    host_type: str | None = None
    confidence: float = 0.0
    reason: str | None = None
    local_path: str | None = None
    final_url: str | None = None
    filename: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    page_count: int | None = None


@dataclass
class PaperRecordDraft:
    """Storage-facing paper DTO.

    This model intentionally does not import search DTOs. It can be constructed
    by an upper-layer facade from search results, local PDF imports, or future
    metadata enrichment workers.
    """

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
    source: str = "unknown"
    landing_url: str | None = None
    fulltext_locations: list[FulltextLocationRecord] = field(default_factory=list)
    score: float = 0.0
    score_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
