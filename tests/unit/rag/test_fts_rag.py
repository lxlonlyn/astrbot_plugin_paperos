from __future__ import annotations

import asyncio

from paperos.rag.service import RagService
from paperos.storage.interfaces import VectorSearchRecord
from paperos.storage.config import StorageConfig
from paperos.storage.models import PaperRecordDraft
from paperos.storage.sqlite.repository import SQLitePaperRepository


class FakeQueryEmbeddingProvider:
    id = "emb-a"
    name = "Fake Query Embeddings"

    async def get_dim(self) -> int:
        return 3

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]


class FakeEmbeddingContext:
    def __init__(self, providers):
        self.providers = providers

    async def get_all_embedding_providers(self):
        return self.providers


class FakeVectorIndex:
    def __init__(self, hits: list[VectorSearchRecord] | None = None):
        self.hits = hits or []
        self.search_calls: list[tuple[list[float], int, str | None]] = []

    async def upsert_vectors(self, records):
        return None

    async def search(self, vector: list[float], *, limit: int = 20, profile: str | None = None):
        self.search_calls.append((vector, limit, profile))
        return self.hits[:limit]


def test_fts_retrieval_and_evidence_pack(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        draft = PaperRecordDraft(
            title="Attention Is All You Need",
            year=2017,
            source="test",
        )
        paper_id = await repo.upsert_paper(draft, source_query="attention")
        version_id = await repo.current_version_id(paper_id)
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            chunks=[
                {
                    "chunk_index": 0,
                    "section_title": "Introduction",
                    "section_path": "Introduction",
                    "text": "Recurrent models are commonly used for sequence transduction.",
                },
                {
                    "chunk_index": 1,
                    "section_title": "Attention",
                    "section_path": "Model Architecture / Attention",
                    "page_start": 3,
                    "page_end": 3,
                    "text": "Scaled dot product attention computes compatibility between queries and keys.",
                },
                {
                    "chunk_index": 2,
                    "section_title": "Training",
                    "section_path": "Training",
                    "text": "Optimization uses Adam and label smoothing.",
                },
            ],
        )

        rag = RagService(repository=repo)
        chunks = await rag.retrieve_local("dot product attention")
        assert chunks
        assert chunks[0].paper_id == paper_id
        assert "attention" in chunks[0].text.lower()

        pack = await rag.build_evidence_pack("dot product attention", chunks[:1])
        assert pack.query == "dot product attention"
        assert len(pack.items) == 1
        assert pack.items[0].citation["title"] == "Attention Is All You Need"
        assert pack.items[0].neighbors
        assert any(neighbor.section_title == "Introduction" for neighbor in pack.items[0].neighbors)

        await repo.aclose()

    asyncio.run(run())


def test_hybrid_retrieval_uses_vector_hits_from_storage_index(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        paper_id = await repo.upsert_paper(PaperRecordDraft(title="Hybrid Paper", source="test"))
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=await repo.current_version_id(paper_id),
            object_id=None,
            chunks=[
                {"chunk_index": 0, "text": "attention evidence from lexical match"},
                {"chunk_index": 1, "text": "transformer representation evidence from vector match"},
            ],
        )
        vector_chunk_id = repo.conn.execute(
            """
            SELECT id FROM paper_chunks
            WHERE paper_id = ? AND chunk_index = 1
            """,
            (paper_id,),
        ).fetchone()["id"]

        vector_index = FakeVectorIndex([VectorSearchRecord(chunk_id=vector_chunk_id, score=0.91)])
        rag = RagService(
            repository=repo,
            vector_index=vector_index,
            context=FakeEmbeddingContext({"emb-a": FakeQueryEmbeddingProvider()}),
        )

        chunks = await rag.retrieve_local("attention")

        assert any(chunk.chunk_id == vector_chunk_id for chunk in chunks)
        vector_chunk = next(chunk for chunk in chunks if chunk.chunk_id == vector_chunk_id)
        assert "vector" in vector_chunk.metadata["retrieval_sources"]
        assert vector_index.search_calls[0][2] == "emb-a:dim3"

        await repo.aclose()

    asyncio.run(run())


def test_hybrid_retrieval_falls_back_to_fts_when_vector_unavailable(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        paper_id = await repo.upsert_paper(PaperRecordDraft(title="Fallback Paper", source="test"))
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=await repo.current_version_id(paper_id),
            object_id=None,
            chunks=[{"text": "attention evidence remains available"}],
        )

        rag = RagService(
            repository=repo,
            vector_index=FakeVectorIndex(),
            context=FakeEmbeddingContext({}),
        )

        chunks = await rag.retrieve_local("attention")

        assert len(chunks) == 1
        assert chunks[0].paper_id == paper_id
        assert chunks[0].metadata["vector_fallback"] is True
        assert "embedding provider" in chunks[0].metadata["vector_fallback_reason"].lower()

        await repo.aclose()

    asyncio.run(run())


def test_fts_retrieval_can_filter_by_paper_id(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()

        first_id = await repo.upsert_paper(PaperRecordDraft(title="First Paper", source="test"))
        second_id = await repo.upsert_paper(PaperRecordDraft(title="Second Paper", source="test"))
        await repo.replace_chunks(
            paper_id=first_id,
            version_id=await repo.current_version_id(first_id),
            object_id=None,
            chunks=[{"text": "attention evidence from first paper"}],
        )
        await repo.replace_chunks(
            paper_id=second_id,
            version_id=await repo.current_version_id(second_id),
            object_id=None,
            chunks=[{"text": "attention evidence from second paper"}],
        )

        rag = RagService(repository=repo)
        chunks = await rag.retrieve_local("attention", filters=None)
        assert {chunk.paper_id for chunk in chunks} == {first_id, second_id}

        from paperos.rag.models import RagFilters

        filtered = await rag.retrieve_local("attention", filters=RagFilters(paper_id=second_id))
        assert [chunk.paper_id for chunk in filtered] == [second_id]

        await repo.aclose()

    asyncio.run(run())
