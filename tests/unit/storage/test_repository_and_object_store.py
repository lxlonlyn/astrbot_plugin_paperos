from __future__ import annotations

import asyncio

from paperos.storage.config import StorageConfig
from paperos.storage.models import FulltextLocationRecord, PaperRecordDraft
from paperos.storage.objects import LocalFileObjectStore
from paperos.storage.sqlite.repository import SQLitePaperRepository


def test_repository_object_store_roundtrip(tmp_path):
    async def run():
        cfg = StorageConfig()
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", cfg)
        await repo.initialize()
        store = LocalFileObjectStore(tmp_path / "objects", tmp_path / "tmp")

        draft = PaperRecordDraft(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            doi="10.5555/attention",
            source="test",
            fulltext_locations=[
                FulltextLocationRecord(
                    url="https://example.test/paper.pdf",
                    source="test",
                    status="verified_pdf",
                    confidence=1.0,
                )
            ],
        )

        paper_id = await repo.upsert_paper(draft, source_query="attention")
        assert paper_id.startswith("p_")
        assert await repo.exists(draft) is True

        stored = await store.put_bytes(
            b"%PDF-1.4\n% test pdf bytes\n",
            kind="pdf",
            suffix=".pdf",
            mime_type="application/pdf",
        )
        object_id = await repo.register_object(stored)
        await repo.attach_object_to_current_version(paper_id=paper_id, object_id=object_id, role="pdf")

        job_id = await repo.enqueue_job(
            "rag_index_pdf",
            dedupe_key=f"rag_index_pdf:{object_id}",
            paper_id=paper_id,
            object_id=object_id,
            payload={"source_query": "attention"},
        )
        claimed = await repo.claim_next_job(worker_id="test-worker")
        assert claimed is not None
        assert claimed["id"] == job_id
        assert claimed["payload"]["source_query"] == "attention"

        await repo.mark_job_done(job_id)
        await repo.aclose()

    asyncio.run(run())

