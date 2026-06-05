from __future__ import annotations

from typing import Protocol

from ..storage.models import ChunkRecord
from .models import RagFilters, RetrievedChunk


class ChunkSearchRepository(Protocol):
    async def search_chunks_fts(
        self,
        query: str,
        *,
        paper_id: str | None = None,
        limit: int = 20,
    ) -> list[ChunkRecord]: ...


class FTSRetriever:
    """FTS-only retriever for RAG Phase 1."""

    def __init__(self, repository: ChunkSearchRepository):
        self.repository = repository

    async def retrieve(self, query: str, *, filters: RagFilters | None = None) -> list[RetrievedChunk]:
        filters = filters or RagFilters()
        records = await self.repository.search_chunks_fts(
            query,
            paper_id=filters.paper_id,
            limit=filters.limit,
        )
        return [retrieved_chunk_from_record(record) for record in records]


def retrieved_chunk_from_record(record: ChunkRecord) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=record.chunk_id,
        paper_id=record.paper_id,
        title=record.title,
        text=record.text,
        score=record.score,
        rank=record.rank,
        section_title=record.section_title,
        section_path=record.section_path,
        page_start=record.page_start,
        page_end=record.page_end,
        chunk_type=record.chunk_type,
        metadata=dict(record.metadata or {}),
    )
