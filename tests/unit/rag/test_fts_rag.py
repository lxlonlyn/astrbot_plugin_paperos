from __future__ import annotations

import asyncio

from paperos.rag.service import RagService
from paperos.storage.config import StorageConfig
from paperos.storage.models import PaperRecordDraft
from paperos.storage.sqlite.repository import SQLitePaperRepository


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
