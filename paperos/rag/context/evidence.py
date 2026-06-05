from __future__ import annotations

from typing import Protocol

from ...storage.models import ChunkRecord
from ..models import EvidenceItem, EvidencePack, RagFilters, RetrievedChunk
from ..retrieval import retrieved_chunk_from_record


class EvidenceRepository(Protocol):
    async def get_neighbor_chunks(
        self,
        chunk_id: str,
        *,
        before: int = 1,
        after: int = 1,
    ) -> list[ChunkRecord]: ...

    async def get_paper_citation_metadata(self, paper_id: str) -> dict: ...


class EvidenceBuilder:
    """Build an evidence pack from retrieved chunks and local storage metadata."""

    def __init__(self, repository: EvidenceRepository):
        self.repository = repository

    async def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        filters: RagFilters | None = None,
    ) -> EvidencePack:
        filters = filters or RagFilters()
        items: list[EvidenceItem] = []
        citation_cache: dict[str, dict] = {}
        for chunk in chunks:
            neighbor_records = await self.repository.get_neighbor_chunks(
                chunk.chunk_id,
                before=filters.neighbor_before,
                after=filters.neighbor_after,
            )
            neighbors = [
                retrieved_chunk_from_record(record)
                for record in neighbor_records
                if record.chunk_id != chunk.chunk_id
            ]
            citation = citation_cache.get(chunk.paper_id)
            if citation is None:
                citation = await self.repository.get_paper_citation_metadata(chunk.paper_id)
                citation_cache[chunk.paper_id] = citation
            items.append(EvidenceItem(chunk=chunk, neighbors=neighbors, citation=citation))
        return EvidencePack(query=query, items=items)
