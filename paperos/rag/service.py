from __future__ import annotations

from typing import Any

from ..config import RagConfig
from ..storage.interfaces import LocalVectorIndex
from .context import EvidenceBuilder
from .models import EvidencePack, RagFilters, RetrievedChunk
from .retrieval import FTSRetriever, HybridRetriever, VectorRetriever


class RagService:
    """Local RAG service backed by storage retrieval surfaces."""

    def __init__(
        self,
        *,
        repository,
        vector_index: LocalVectorIndex | None = None,
        context: Any | None = None,
        cfg: RagConfig | None = None,
    ):
        self.repository = repository
        self.retriever = FTSRetriever(repository)
        self.vector_retriever = (
            VectorRetriever(
                repository=repository,
                vector_index=vector_index,
                context=context,
                cfg=cfg,
            )
            if vector_index is not None and context is not None
            else None
        )
        self.hybrid_retriever = (
            HybridRetriever(fts=self.retriever, vector=self.vector_retriever)
            if self.vector_retriever is not None
            else None
        )
        self.evidence_builder = EvidenceBuilder(repository)

    async def retrieve_local(
        self,
        query: str,
        filters: RagFilters | None = None,
    ) -> list[RetrievedChunk]:
        if self.hybrid_retriever is None:
            return await self.retriever.retrieve(query, filters=filters)
        try:
            return await self.hybrid_retriever.retrieve(query, filters=filters)
        except Exception as exc:
            chunks = await self.retriever.retrieve(query, filters=filters)
            return [_with_fallback_metadata(chunk, str(exc)) for chunk in chunks]

    async def build_evidence_pack(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        filters: RagFilters | None = None,
    ) -> EvidencePack:
        return await self.evidence_builder.build(query, chunks, filters=filters)

    async def retrieve_evidence(
        self,
        query: str,
        filters: RagFilters | None = None,
    ) -> EvidencePack:
        chunks = await self.retrieve_local(query, filters=filters)
        return await self.build_evidence_pack(query, chunks, filters=filters)


def _with_fallback_metadata(chunk: RetrievedChunk, reason: str) -> RetrievedChunk:
    from dataclasses import replace

    metadata = dict(chunk.metadata or {})
    metadata["vector_fallback"] = True
    metadata["vector_fallback_reason"] = reason
    return replace(chunk, metadata=metadata)
