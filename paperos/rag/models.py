from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RagFilters:
    paper_id: str | None = None
    limit: int = 8
    vector_limit: int | None = None
    fts_limit: int | None = None
    neighbor_before: int = 1
    neighbor_after: int = 1


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    paper_id: str
    title: str
    text: str
    score: float = 0.0
    rank: int | None = None
    section_title: str | None = None
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_type: str = "paragraph"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItem:
    chunk: RetrievedChunk
    neighbors: list[RetrievedChunk] = field(default_factory=list)
    citation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidencePack:
    query: str
    items: list[EvidenceItem] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.items
