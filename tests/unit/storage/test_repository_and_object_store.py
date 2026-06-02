from __future__ import annotations

import asyncio
import sqlite3

from paperos.storage.config import StorageConfig
from paperos.storage.diagnostics import StorageDiagnostics
from paperos.storage.factory import PaperOSStorageContext
from paperos.storage.importer import PaperImportRequest, PaperStorageImporter
from paperos.storage.models import FulltextLocationRecord, PaperRecordDraft
from paperos.storage.objects import LocalFileObjectStore
from paperos.storage.paths import PaperOSPaths
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


def test_initialize_rebuilds_early_incompatible_schema(tmp_path):
    db_path = tmp_path / "paperos.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE fulltext_locations (
                id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                version_id TEXT,
                url TEXT NOT NULL,
                source TEXT,
                kind TEXT,
                status TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, name, applied_at)
            VALUES (1, 'initial_storage_schema', '2026-01-01T00:00:00+00:00');
            """
        )
    finally:
        conn.close()

    async def run():
        repo = SQLitePaperRepository(db_path, StorageConfig())
        await repo.initialize()
        columns = {
            row["name"]
            for row in repo.conn.execute("PRAGMA table_info(fulltext_locations)").fetchall()
        }
        assert "object_id" in columns
        assert "final_url" in columns
        assert "page_count" in columns
        assert repo.conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
        await repo.aclose()

    asyncio.run(run())


def test_paths_create_plugin_data_index_subdirectories(tmp_path):
    cfg = StorageConfig(root_dir=str(tmp_path / "paperos_data"))
    paths = PaperOSPaths.from_config(cfg, plugin_name="astrbot_plugin_paperos")
    paths.ensure_dirs()

    assert paths.database_path == paths.root_dir / "paperos.sqlite3"
    assert paths.object_dir == paths.root_dir / "objects"
    assert paths.index_dir == paths.root_dir / "indexes"
    assert paths.fts_index_dir == paths.root_dir / "indexes" / "fts"
    assert paths.vector_index_dir == paths.root_dir / "indexes" / "vector"
    assert paths.fts_index_dir.is_dir()
    assert paths.vector_index_dir.is_dir()


def test_storage_diagnostics_status_and_info(tmp_path):
    async def run():
        paths = PaperOSPaths.from_config(StorageConfig(root_dir=str(tmp_path / "paperos_data")))
        paths.ensure_dirs()
        repo = SQLitePaperRepository(paths.database_path, StorageConfig(root_dir=str(paths.root_dir)))
        await repo.initialize()
        store = LocalFileObjectStore(paths.object_dir, paths.tmp_dir)
        context = PaperOSStorageContext(
            cfg=StorageConfig(root_dir=str(paths.root_dir)),
            paths=paths,
            repository=repo,
            object_store=store,
        )

        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n% verified upstream\n")
        importer = PaperStorageImporter(repository=repo, object_store=store)
        result = await importer.import_paper(
            PaperImportRequest(
                record=PaperRecordDraft(
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    year=2017,
                    venue="NeurIPS",
                    doi="10.5555/attention",
                    arxiv_id="1706.03762",
                    source="test",
                    fulltext_locations=[
                        FulltextLocationRecord(
                            url="https://example.test/attention.pdf",
                            source="test",
                            status="verified_pdf",
                            confidence=1.0,
                            local_path=str(pdf_path),
                            size_bytes=pdf_path.stat().st_size,
                            content_type="application/pdf",
                            page_count=15,
                        )
                    ],
                ),
                source_query="attention",
            )
        )

        diagnostics = StorageDiagnostics(context)
        status = diagnostics.status(enabled=True)
        assert status.schema_version == 1
        assert status.stats.papers == 1
        assert status.stats.objects == 1
        assert status.stats.pdf_objects == 1
        assert status.stats.fulltext_locations == 1
        assert status.stats.jobs_by_status["pending"] == 1

        info = diagnostics.paper_info("10.5555/attention")
        assert info.found is True
        assert info.paper_id == result.paper_id
        assert info.title == "Attention Is All You Need"
        assert ("doi", "10.5555/attention") in info.identifiers
        assert info.objects[0].object_id == result.object_id
        assert info.objects[0].file_exists is True
        assert info.verified_pdf_status and "verified_pdf" in info.verified_pdf_status
        assert info.chunk_count == 0
        assert info.recent_jobs[0].status == "pending"

        await repo.aclose()

    asyncio.run(run())
