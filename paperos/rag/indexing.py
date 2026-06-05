from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..config import RagConfig
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


class VectorStore(Protocol):
    async def upsert_vectors(self, records: list[dict[str, Any]]) -> None: ...


class LanceDBVectorStore:
    def __init__(self, path: Path, *, table_name: str = "chunk_embeddings"):
        self.path = Path(path)
        self.table_name = table_name

    async def upsert_vectors(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        try:
            import lancedb  # type: ignore
        except Exception as exc:
            raise RagIndexError(
                "LanceDB is not installed. Install the plugin requirements or add lancedb "
                "before running RAG vector indexing."
            ) from exc

        self.path.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(self.path))
        table_names = set(db.table_names())
        if self.table_name not in table_names:
            db.create_table(self.table_name, data=records)
            return

        table = db.open_table(self.table_name)
        for record in records:
            table.delete(
                "chunk_id = "
                + _quote_lancedb_value(str(record["chunk_id"]))
                + " AND embedding_model = "
                + _quote_lancedb_value(str(record["embedding_model"]))
            )
        table.add(records)


class RagIndexService:
    """Embed storage chunks and write rebuildable vector index records."""

    def __init__(
        self,
        *,
        repository: RagIndexRepository,
        context: Any,
        vector_index_dir: Path,
        cfg: RagConfig | None = None,
        vector_store: VectorStore | None = None,
    ):
        self.repository = repository
        self.context = context
        self.cfg = cfg or RagConfig()
        self.vector_store = vector_store or LanceDBVectorStore(
            vector_index_dir,
            table_name=self.cfg.vector_table_name,
        )

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
        for paper_id in paper_ids:
            await self.repository.update_index_status(
                paper_id=paper_id,
                index_name=self.cfg.vector_table_name,
                status="indexing",
                profile=profile,
                message=f"embedding {len(chunks)} chunks",
            )

        try:
            records = await self._embed_records(chunks, resolved.provider, resolved.provider_id, resolved.dim, profile)
            await self.vector_store.upsert_vectors(records)
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
            count = sum(1 for chunk in chunks if chunk.paper_id == paper_id)
            await self.repository.update_index_status(
                paper_id=paper_id,
                index_name=self.cfg.vector_table_name,
                status="done",
                profile=profile,
                message=f"indexed {count} chunks",
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
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
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
                {
                    "id": f"{chunk.chunk_id}:{profile}:{content_hash}",
                    "chunk_id": chunk.chunk_id,
                    "paper_id": chunk.paper_id,
                    "vector": vector,
                    "embedding_model": profile,
                    "provider_id": provider_id,
                    "content_hash": content_hash,
                    "section_path": chunk.section_path,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "chunk_type": chunk.chunk_type,
                    "parser_run_id": chunk.parser_run_id,
                    "chunk_index": chunk.chunk_index,
                    "text": text,
                }
            )
        return out


def _embedding_text(chunk: ChunkRecord) -> str:
    return chunk.embedding_text or chunk.text


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _index_profile(provider_id: str, dim: int) -> str:
    raw = f"{provider_id or 'astrbot_embedding'}:dim{dim}"
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_")


def _quote_lancedb_value(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
