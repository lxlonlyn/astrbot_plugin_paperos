from __future__ import annotations

import asyncio

from paperos.config import RagConfig
from paperos.rag.indexing import RagIndexService
from paperos.rag.providers import EmbeddingProviderError, resolve_embedding_provider
from paperos.storage.config import StorageConfig
from paperos.storage.interfaces import ChunkEmbeddingStatusDraft, VectorRecord
from paperos.storage.models import PaperRecordDraft
from paperos.storage.sqlite.repository import SQLitePaperRepository


class FakeEmbeddingProvider:
    id = "emb-a"
    name = "Fake Embeddings"

    def __init__(self):
        self.calls: list[list[str]] = []

    async def get_dim(self) -> int:
        return 3

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(len(text)), 1.0, 0.5] for text in texts]


class FakeBatchEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(self):
        super().__init__()
        self.batch_calls: list[tuple[list[str], int]] = []

    async def get_embeddings_batch(self, texts: list[str], batch_size: int = 16, **kwargs):
        self.batch_calls.append((texts, batch_size))
        return [[float(len(text)), 1.0, 0.5] for text in texts]


class FakeEmbeddingContext:
    def __init__(self, providers):
        self.providers = providers

    async def get_all_embedding_providers(self):
        return self.providers


class FakeVectorStore:
    def __init__(self):
        self.records: list[VectorRecord] = []

    async def upsert_vectors(self, records: list[VectorRecord]) -> None:
        self.records.extend(records)

    async def search(self, vector: list[float], *, limit: int = 20, profile: str | None = None):
        return []


def test_resolve_embedding_provider_requires_explicit_choice_when_multiple():
    async def run():
        context = FakeEmbeddingContext(
            {
                "emb-a": FakeEmbeddingProvider(),
                "emb-b": FakeEmbeddingProvider(),
            }
        )

        try:
            await resolve_embedding_provider(context)
        except EmbeddingProviderError as exc:
            assert "Multiple AstrBot embedding providers" in str(exc)
        else:
            raise AssertionError("expected resolver to require provider id")

        resolved = await resolve_embedding_provider(context, provider_id="emb-a")
        assert resolved.provider_id == "emb-a"
        assert resolved.dim == 3

    asyncio.run(run())


def test_rag_index_service_indexes_paper_chunks_and_updates_index_status(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        paper_id = await repo.upsert_paper(PaperRecordDraft(title="Indexed Paper", source="test"))
        version_id = await repo.current_version_id(paper_id)
        parser_run_id = "pr_index_test"
        now = "2026-01-01T00:00:00+00:00"
        repo.conn.execute(
            """
            INSERT INTO parser_runs(
                id, paper_id, version_id, object_id, parser_name, parser_version,
                status, message, created_at, updated_at
            )
            VALUES (?, ?, ?, NULL, 'test-parser', '1', 'done', NULL, ?, ?)
            """,
            (parser_run_id, paper_id, version_id, now, now),
        )
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            parser_run_id=parser_run_id,
            chunks=[
                {
                    "chunk_index": 0,
                    "section_path": "Intro",
                    "text": "raw chunk text",
                    "embedding_text": "formatted embedding text",
                    "content_hash": "hash-1",
                }
            ],
        )

        provider = FakeEmbeddingProvider()
        vector_index = FakeVectorStore()
        service = RagIndexService(
            repository=repo,
            vector_index=vector_index,
            context=FakeEmbeddingContext({"emb-a": provider}),
            cfg=RagConfig(embedding_batch_size=2),
        )

        result = await service.index_parser_run(parser_run_id)

        assert result.paper_ids == [paper_id]
        assert result.chunk_count == 1
        assert result.vector_count == 1
        assert provider.calls == [["formatted embedding text"]]
        assert vector_index.records[0].paper_id == paper_id
        assert vector_index.records[0].content_hash == "hash-1"
        assert vector_index.records[0].embedding_model == "emb-a:dim3"
        assert not hasattr(vector_index.records[0], "text")

        status = repo.conn.execute(
            """
            SELECT status, profile, message
            FROM index_status
            WHERE paper_id = ? AND index_name = 'chunk_embeddings'
            """,
            (paper_id,),
        ).fetchone()
        assert status["status"] == "done"
        assert status["profile"] == "emb-a:dim3"
        assert status["message"] == "indexed 1 missing/stale chunks"

        chunk_status = repo.conn.execute(
            """
            SELECT status, vector_backend, vector_profile, vector_table
            FROM chunk_embedding_status
            WHERE paper_id = ?
            """,
            (paper_id,),
        ).fetchone()
        assert chunk_status["status"] == "done"
        assert chunk_status["vector_backend"] == "storage"
        assert chunk_status["vector_profile"] == "emb-a:dim3"
        assert chunk_status["vector_table"] == "chunk_embeddings"

        await repo.aclose()

    asyncio.run(run())


def test_rag_index_service_prefers_astrbot_batch_embedding_helper(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        paper_id = await repo.upsert_paper(PaperRecordDraft(title="Batch Indexed Paper", source="test"))
        version_id = await repo.current_version_id(paper_id)
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            chunks=[
                {"chunk_index": 0, "text": "chunk zero"},
                {"chunk_index": 1, "text": "chunk one"},
                {"chunk_index": 2, "text": "chunk two"},
            ],
        )

        provider = FakeBatchEmbeddingProvider()
        service = RagIndexService(
            repository=repo,
            vector_index=FakeVectorStore(),
            context=FakeEmbeddingContext({"emb-a": provider}),
            cfg=RagConfig(embedding_batch_size=2),
        )

        result = await service.index_paper(paper_id)

        assert result.vector_count == 3
        assert provider.batch_calls == [(["chunk zero", "chunk one", "chunk two"], 2)]
        assert provider.calls == []

        await repo.aclose()

    asyncio.run(run())


def test_rag_index_service_skips_chunks_with_current_embedding_status(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        paper_id = await repo.upsert_paper(PaperRecordDraft(title="Already Indexed Paper", source="test"))
        version_id = await repo.current_version_id(paper_id)
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            chunks=[
                {
                    "chunk_index": 0,
                    "text": "already embedded",
                    "content_hash": "hash-current",
                }
            ],
        )
        chunk_id = repo.conn.execute(
            "SELECT id FROM paper_chunks WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()["id"]
        await repo.upsert_chunk_embedding_status(
            ChunkEmbeddingStatusDraft(
                chunk_id=chunk_id,
                paper_id=paper_id,
                content_hash="hash-current",
                embedding_provider_id="emb-a",
                embedding_model="emb-a:dim3",
                embedding_dim=3,
                vector_backend="storage",
                vector_profile="emb-a:dim3",
                vector_table="chunk_embeddings",
                status="done",
            )
        )

        provider = FakeEmbeddingProvider()
        vector_index = FakeVectorStore()
        service = RagIndexService(
            repository=repo,
            vector_index=vector_index,
            context=FakeEmbeddingContext({"emb-a": provider}),
            cfg=RagConfig(embedding_batch_size=2),
        )

        result = await service.index_paper(paper_id)

        assert result.chunk_count == 1
        assert result.vector_count == 0
        assert provider.calls == []
        assert vector_index.records == []

        await repo.aclose()

    asyncio.run(run())
