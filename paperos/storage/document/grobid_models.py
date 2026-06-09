from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentSection:
    title: str
    level: int = 0
    order_index: int = 0
    parent_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class DocumentBlock:
    block_index: int
    block_type: str
    text: str
    section_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    coords: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None


@dataclass(frozen=True)
class DocumentReference:
    raw_text: str
    ref_key: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class DocumentAsset:
    asset_type: str
    label: str | None = None
    caption: str | None = None
    page: int | None = None
    coords: dict[str, Any] = field(default_factory=dict)
    object_id: str | None = None
    text_object_id: str | None = None
    linked_block_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDocument:
    title: str | None = None
    abstract: str | None = None
    sections: list[DocumentSection] = field(default_factory=list)
    blocks: list[DocumentBlock] = field(default_factory=list)
    assets: list[DocumentAsset] = field(default_factory=list)
    references: list[DocumentReference] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
