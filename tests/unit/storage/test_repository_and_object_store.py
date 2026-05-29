from __future__ import annotations

import asyncio

from paperos.storage.config import StorageConfig
from paperos.storage.importer import PaperImportRequest, PaperStorageImporter
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


def test_storage_importer_persists_verified_pdf_and_provenance(tmp_path):
    async def run():
        pdf_path = tmp_path / "searcher" / "fulltext" / "paper.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"%PDF-1.4\n% verified upstream\n")

        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()
        store = LocalFileObjectStore(tmp_path / "objects", tmp_path / "tmp")
        importer = PaperStorageImporter(repository=repo, object_store=store)

        record = PaperRecordDraft(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            doi="10.5555/attention",
            source="test",
            fulltext_locations=[
                FulltextLocationRecord(
                    url="https://example.test/attention.pdf",
                    final_url="https://cdn.example.test/attention.pdf",
                    source="test",
                    status="verified_pdf",
                    confidence=1.0,
                    local_path=str(pdf_path),
                    filename="paper.pdf",
                    sha256="a" * 64,
                    size_bytes=pdf_path.stat().st_size,
                    content_type="application/pdf",
                    page_count=15,
                )
            ],
        )

        result = await importer.import_paper(
            PaperImportRequest(
                record=record,
                source_query="attention",
                cleanup_source_file=True,
            )
        )

        assert result.imported_pdf is True
        assert result.object_id
        assert result.job_id
        assert result.source_file_removed is True
        assert not pdf_path.exists()

        row = repo.conn.execute(
            """
            SELECT object_id, final_url, filename, sha256, size_bytes, content_type, page_count
            FROM fulltext_locations
            WHERE paper_id = ? AND url = ?
            """,
            (result.paper_id, "https://example.test/attention.pdf"),
        ).fetchone()
        assert row is not None
        assert row["object_id"] == result.object_id
        assert row["final_url"] == "https://cdn.example.test/attention.pdf"
        assert row["filename"] == "paper.pdf"
        assert row["sha256"] == "a" * 64
        assert row["size_bytes"] == len(b"%PDF-1.4\n% verified upstream\n")
        assert row["content_type"] == "application/pdf"
        assert row["page_count"] == 15

        await repo.aclose()

    asyncio.run(run())
