from __future__ import annotations

from .context import EvidenceBuilder
from .models import EvidencePack, RagFilters, RetrievedChunk
from .retrieval import FTSRetriever


class RagService:
    """Phase 1 local RAG service backed by storage FTS."""

    def __init__(self, *, repository):
        self.repository = repository
        self.retriever = FTSRetriever(repository)
        self.evidence_builder = EvidenceBuilder(repository)

    async def retrieve_local(
        self,
        query: str,
        filters: RagFilters | None = None,
    ) -> list[RetrievedChunk]:
        return await self.retriever.retrieve(query, filters=filters)

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
