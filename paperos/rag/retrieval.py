from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Protocol

from ..config import RagConfig
from ..storage.interfaces import LocalVectorIndex
from ..storage.models import ChunkRecord
from .models import RagFilters, RetrievedChunk
from .providers import get_embeddings, resolve_embedding_provider


class ChunkSearchRepository(Protocol):
    async def search_chunks_fts(
        self,
        query: str,
        *,
        paper_id: str | None = None,
        limit: int = 20,
    ) -> list[ChunkRecord]: ...

    async def get_chunks_by_ids(self, ids: list[str]) -> list[ChunkRecord]: ...


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


class VectorRetriever:
    """Query-vector retriever backed by a storage-owned vector index."""

    def __init__(
        self,
        *,
        repository: ChunkSearchRepository,
        vector_index: LocalVectorIndex,
        context: Any,
        cfg: RagConfig | None = None,
    ):
        self.repository = repository
        self.vector_index = vector_index
        self.context = context
        self.cfg = cfg or RagConfig()

    async def retrieve(self, query: str, *, filters: RagFilters | None = None) -> list[RetrievedChunk]:
        filters = filters or RagFilters()
        resolved = await resolve_embedding_provider(
            self.context,
            provider_id=self.cfg.embedding_provider_id,
        )
        vectors = await get_embeddings(resolved.provider, [query])
        if not vectors:
            return []

        profile = _vector_profile(resolved.provider_id or resolved.name, resolved.dim)
        limit = filters.vector_limit or filters.limit
        hits = await self.vector_index.search(vectors[0], limit=limit, profile=profile)
        if not hits:
            return []

        hit_by_id = {hit.chunk_id: hit for hit in hits}
        records = await self.repository.get_chunks_by_ids([hit.chunk_id for hit in hits])
        record_by_id = {record.chunk_id: record for record in records}
        chunks: list[RetrievedChunk] = []
        for rank, hit in enumerate(hits, start=1):
            record = record_by_id.get(hit.chunk_id)
            if record is None:
                continue
            hit = hit_by_id.get(record.chunk_id)
            if hit is None:
                continue
            if filters.paper_id and record.paper_id != filters.paper_id:
                continue
            chunks.append(
                retrieved_chunk_from_record(
                    replace(record, score=hit.score, rank=rank),
                    source="vector",
                )
            )
        return chunks


class HybridRetriever:
    """Combine FTS and vector retrieval with reciprocal-rank fusion."""

    def __init__(self, *, fts: FTSRetriever, vector: VectorRetriever):
        self.fts = fts
        self.vector = vector

    async def retrieve(self, query: str, *, filters: RagFilters | None = None) -> list[RetrievedChunk]:
        filters = filters or RagFilters()
        fts_filters = _with_limit(filters, filters.fts_limit or filters.limit)
        vector_filters = _with_limit(filters, filters.vector_limit or filters.limit)
        fts_chunks = await self.fts.retrieve(query, filters=fts_filters)
        vector_chunks = await self.vector.retrieve(query, filters=vector_filters)
        return fuse_retrieved_chunks(fts_chunks, vector_chunks, limit=filters.limit)


def fuse_retrieved_chunks(
    fts_chunks: list[RetrievedChunk],
    vector_chunks: list[RetrievedChunk],
    *,
    limit: int,
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    by_id: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}

    for rank, chunk in enumerate(fts_chunks, start=1):
        by_id.setdefault(chunk.chunk_id, chunk)
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
        sources.setdefault(chunk.chunk_id, set()).add("fts")

    for rank, chunk in enumerate(vector_chunks, start=1):
        by_id.setdefault(chunk.chunk_id, chunk)
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
        sources.setdefault(chunk.chunk_id, set()).add("vector")

    ordered_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    out: list[RetrievedChunk] = []
    for rank, chunk_id in enumerate(ordered_ids[: max(1, int(limit))], start=1):
        chunk = by_id[chunk_id]
        metadata = dict(chunk.metadata or {})
        metadata["retrieval_sources"] = sorted(sources.get(chunk_id, set()))
        out.append(replace(chunk, score=scores[chunk_id], rank=rank, metadata=metadata))
    return out


def retrieved_chunk_from_record(record: ChunkRecord, *, source: str = "fts") -> RetrievedChunk:
    metadata = dict(record.metadata or {})
    metadata.setdefault("retrieval_sources", [source])
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
        metadata=metadata,
    )


def _with_limit(filters: RagFilters, limit: int) -> RagFilters:
    return replace(filters, limit=max(1, int(limit)))


def _vector_profile(provider_id: str, dim: int) -> str:
    raw = f"{provider_id or 'astrbot_embedding'}:dim{dim}"
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_")
