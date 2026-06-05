from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Protocol

from ..config import RagConfig
from ..storage.interfaces import (
    ChunkEmbeddingStatusDraft,
    LocalVectorIndex,
    VectorRecord,
)
from ..storage.models import ChunkRecord
from .providers import EmbeddingProviderError, get_embeddings_batched, resolve_embedding_provider


class RagIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class RagIndexResult:
    paper_ids: list[str]
    chunk_count: int
    vector_count: int
    provider_id: str
    embedding_dim: int
    index_name: str
    profile: str


class RagIndexRepository(Protocol):
    async def get_chunks_for_parser_run(self, parser_run_id: str) -> list[ChunkRecord]: ...

    async def get_chunks_for_paper(self, paper_id: str) -> list[ChunkRecord]: ...

    async def update_index_status(
        self,
        *,
        paper_id: str,
        index_name: str,
        status: str,
        profile: str | None = None,
        message: str | None = None,
    ) -> None: ...

    async def get_chunk_embedding_status(
        self,
        *,
        chunk_id: str,
        content_hash: str,
        embedding_provider_id: str,
        embedding_model: str,
        embedding_dim: int,
        vector_profile: str,
    ) -> object | None: ...

    async def upsert_chunk_embedding_status(
        self,
        draft: ChunkEmbeddingStatusDraft,
    ) -> str: ...

    async def list_missing_or_stale_chunk_embeddings(
        self,
        *,
        paper_id: str | None = None,
        parser_run_id: str | None = None,
        embedding_provider_id: str,
        embedding_model: str,
        embedding_dim: int,
        vector_profile: str,
        limit: int = 100,
    ) -> list[ChunkRecord]: ...


class RagIndexService:
    """Compute chunk embeddings and write them through storage-owned interfaces."""

    def __init__(
        self,
        *,
        repository: RagIndexRepository,
        vector_index: LocalVectorIndex,
        context: Any,
        cfg: RagConfig | None = None,
    ):
        self.repository = repository
        self.vector_index = vector_index
        self.context = context
        self.cfg = cfg or RagConfig()

    async def index_parser_run(self, parser_run_id: str) -> RagIndexResult:
        chunks = await self.repository.get_chunks_for_parser_run(parser_run_id)
        if not chunks:
            raise RagIndexError(f"No chunks found for parser_run_id={parser_run_id!r}.")
        return await self._index_chunks(chunks)

    async def index_paper(self, paper_id: str) -> RagIndexResult:
        chunks = await self.repository.get_chunks_for_paper(paper_id)
        if not chunks:
            raise RagIndexError(f"No chunks found for paper_id={paper_id!r}.")
        return await self._index_chunks(chunks)

    async def index_pending_job(self, job: dict[str, Any]) -> RagIndexResult:
        payload = job.get("payload") or job.get("payload_json") or {}
        if isinstance(payload, str):
            raise RagIndexError("RAG index job payload must be decoded before calling RagIndexService.")
        parser_run_id = payload.get("parser_run_id")
        if parser_run_id:
            return await self.index_parser_run(str(parser_run_id))
        paper_id = payload.get("paper_id") or job.get("paper_id")
        if paper_id:
            return await self.index_paper(str(paper_id))
        raise RagIndexError("RAG index job requires payload.parser_run_id or paper_id.")

    async def _index_chunks(self, chunks: list[ChunkRecord]) -> RagIndexResult:
        paper_ids = sorted({chunk.paper_id for chunk in chunks})
        resolved = await resolve_embedding_provider(
            self.context,
            provider_id=self.cfg.embedding_provider_id,
        )
        profile = _index_profile(resolved.provider_id or resolved.name, resolved.dim)
        chunks_to_index = await self._filter_missing_or_stale_chunks(
            chunks,
            provider_id=resolved.provider_id,
            embedding_model=profile,
            embedding_dim=resolved.dim,
            vector_profile=profile,
        )

        for paper_id in paper_ids:
            await self.repository.update_index_status(
                paper_id=paper_id,
                index_name=self.cfg.vector_table_name,
                status="indexing",
                profile=profile,
                message=f"embedding {len(chunks_to_index)} missing/stale chunks",
            )

        try:
            records = await self._embed_records(
                chunks_to_index,
                resolved.provider,
                resolved.provider_id,
                resolved.dim,
                profile,
            )
            await self.vector_index.upsert_vectors(records)
            await self._mark_chunk_embeddings_done(
                records,
                provider_id=resolved.provider_id,
                embedding_dim=resolved.dim,
                vector_profile=profile,
            )
        except Exception as exc:
            for paper_id in paper_ids:
                await self.repository.update_index_status(
                    paper_id=paper_id,
                    index_name=self.cfg.vector_table_name,
                    status="failed",
                    profile=profile,
                    message=str(exc),
                )
            raise

        for paper_id in paper_ids:
            count = sum(1 for chunk in chunks_to_index if chunk.paper_id == paper_id)
            await self.repository.update_index_status(
                paper_id=paper_id,
                index_name=self.cfg.vector_table_name,
                status="done",
                profile=profile,
                message=f"indexed {count} missing/stale chunks",
            )
        return RagIndexResult(
            paper_ids=paper_ids,
            chunk_count=len(chunks),
            vector_count=len(records),
            provider_id=resolved.provider_id,
            embedding_dim=resolved.dim,
            index_name=self.cfg.vector_table_name,
            profile=profile,
        )

    async def _embed_records(
        self,
        chunks: list[ChunkRecord],
        provider: Any,
        provider_id: str,
        dim: int,
        profile: str,
    ) -> list[VectorRecord]:
        out: list[VectorRecord] = []
        batch_size = max(1, int(self.cfg.embedding_batch_size))
        texts = [_embedding_text(chunk) for chunk in chunks]
        vectors = await get_embeddings_batched(provider, texts, batch_size=batch_size)
        for chunk, text, vector in zip(chunks, texts, vectors):
            if len(vector) != dim:
                raise EmbeddingProviderError(
                    f"Embedding dim mismatch for chunk {chunk.chunk_id}: expected {dim}, got {len(vector)}."
                )
            content_hash = chunk.content_hash or _sha256_text(text)
            out.append(
                VectorRecord(
                    id=f"{chunk.chunk_id}:{profile}:{content_hash}",
                    chunk_id=chunk.chunk_id,
                    paper_id=chunk.paper_id,
                    vector=vector,
                    embedding_model=profile,
                    provider_id=provider_id,
                    content_hash=content_hash,
                    parser_run_id=chunk.parser_run_id,
                    chunk_index=chunk.chunk_index,
                    section_path=chunk.section_path,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_type=chunk.chunk_type,
                    profile=profile,
                )
            )
        return out

    async def _filter_missing_or_stale_chunks(
        self,
        chunks: list[ChunkRecord],
        *,
        provider_id: str,
        embedding_model: str,
        embedding_dim: int,
        vector_profile: str,
    ) -> list[ChunkRecord]:
        if not chunks:
            return []
        paper_ids = {chunk.paper_id for chunk in chunks}
        parser_run_ids = {chunk.parser_run_id for chunk in chunks if chunk.parser_run_id}
        if len(parser_run_ids) == 1:
            return await self.repository.list_missing_or_stale_chunk_embeddings(
                parser_run_id=next(iter(parser_run_ids)),
                embedding_provider_id=provider_id,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                vector_profile=vector_profile,
                limit=max(1, len(chunks)),
            )
        if len(paper_ids) == 1:
            return await self.repository.list_missing_or_stale_chunk_embeddings(
                paper_id=next(iter(paper_ids)),
                embedding_provider_id=provider_id,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                vector_profile=vector_profile,
                limit=max(1, len(chunks)),
            )

        out: list[ChunkRecord] = []
        for chunk in chunks:
            content_hash = chunk.content_hash or _sha256_text(_embedding_text(chunk))
            status = await self.repository.get_chunk_embedding_status(
                chunk_id=chunk.chunk_id,
                content_hash=content_hash,
                embedding_provider_id=provider_id,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                vector_profile=vector_profile,
            )
            if status is None or getattr(status, "status", None) != "done":
                out.append(chunk)
        return out

    async def _mark_chunk_embeddings_done(
        self,
        records: list[VectorRecord],
        *,
        provider_id: str,
        embedding_dim: int,
        vector_profile: str,
    ) -> None:
        for record in records:
            await self.repository.upsert_chunk_embedding_status(
                ChunkEmbeddingStatusDraft(
                    chunk_id=record.chunk_id,
                    paper_id=record.paper_id,
                    parser_run_id=record.parser_run_id,
                    content_hash=record.content_hash,
                    embedding_provider_id=provider_id,
                    embedding_model=record.embedding_model,
                    embedding_dim=embedding_dim,
                    vector_backend="storage",
                    vector_profile=vector_profile,
                    vector_table=self.cfg.vector_table_name,
                    status="done",
                )
            )


def _embedding_text(chunk: ChunkRecord) -> str:
    return chunk.embedding_text or chunk.text


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _index_profile(provider_id: str, dim: int) -> str:
    raw = f"{provider_id or 'astrbot_embedding'}:dim{dim}"
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_")
