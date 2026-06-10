from __future__ import annotations

import asyncio
import sqlite3

from paperos.storage.config import StorageConfig
from paperos.storage.diagnostics import StorageDiagnostics
from paperos.storage.document.grobid_models import DocumentBlock, DocumentSection, NormalizedDocument
from paperos.storage.factory import PaperOSStorageContext
from paperos.storage.importer import PaperImportRequest, PaperStorageImporter
from paperos.storage.interfaces import ChunkEmbeddingStatusDraft
from paperos.storage.models import FulltextLocationRecord, PaperRecordDraft
from paperos.storage.objects import LocalFileObjectStore
from paperos.storage.paths import PaperOSPaths
from paperos.storage.sqlite.repository import SQLitePaperRepository
from paperos.storage.vector import LanceDBVectorIndex


class FakeDocumentProcessor:
    async def process_pdf(self, pdf_path):
        document = NormalizedDocument(
            title="Attention Is All You Need",
            sections=[DocumentSection(title="Introduction", order_index=0, level=1)],
            blocks=[
                DocumentBlock(
                    block_index=0,
                    block_type="paragraph",
                    text="This is parsed document text.",
                    section_index=0,
                    content_hash="hash-parsed",
                )
            ],
        )
        normalized = {
            "title": document.title,
            "sections": [{"title": "Introduction"}],
            "blocks": [{"text": "This is parsed document text."}],
        }
        chunks = [
            {
                "chunk_type": "paragraph",
                "section_title": "Introduction",
                "section_path": "Introduction",
                "text": "This is parsed document text.",
                "embedding_text": "Paper: Attention Is All You Need\nSection: Introduction\nType: paragraph\n\nContent:\nThis is parsed document text.",
                "content_hash": "hash-parsed",
                "source_block_ids": [0],
            }
        ]
        return "<TEI>parsed</TEI>", document, normalized, chunks


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
            "storage_parse_pdf",
            dedupe_key=f"storage_parse_pdf:{object_id}",
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
        importer = PaperStorageImporter(
            repository=repo,
            object_store=store,
            document_processor=FakeDocumentProcessor(),
        )

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
        assert result.parser_run_id
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
        job = repo.conn.execute("SELECT job_type FROM paper_jobs WHERE id = ?", (result.job_id,)).fetchone()
        assert job["job_type"] == "storage_parse_pdf"
        job_status = repo.conn.execute("SELECT status FROM paper_jobs WHERE id = ?", (result.job_id,)).fetchone()
        assert job_status["status"] == "done"
        embed_job = repo.conn.execute("SELECT id FROM paper_jobs WHERE job_type = 'rag_embed_chunks'").fetchone()
        assert embed_job is not None
        parser_run = repo.conn.execute(
            """
            SELECT status, raw_output_object_id, normalized_object_id
            FROM parser_runs WHERE id = ?
            """,
            (result.parser_run_id,),
        ).fetchone()
        assert parser_run["status"] == "done"
        assert parser_run["raw_output_object_id"]
        assert parser_run["normalized_object_id"]
        raw_obj = repo.conn.execute("SELECT kind FROM objects WHERE id = ?", (parser_run["raw_output_object_id"],)).fetchone()
        normalized_obj = repo.conn.execute("SELECT kind FROM objects WHERE id = ?", (parser_run["normalized_object_id"],)).fetchone()
        assert raw_obj["kind"] == "tei_xml"
        assert normalized_obj["kind"] == "normalized_document"
        chunk = repo.conn.execute("SELECT text, embedding_text FROM paper_chunks WHERE parser_run_id = ?", (result.parser_run_id,)).fetchone()
        assert chunk["text"] == "This is parsed document text."
        assert chunk["embedding_text"].startswith("Paper: Attention Is All You Need")

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


def test_document_processing_schema_and_extended_chunks(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()
        draft = PaperRecordDraft(title="Attention Is All You Need", year=2017, doi="10.5555/attention", source="test")
        paper_id = await repo.upsert_paper(draft, source_query="attention")
        version_id = repo.conn.execute("SELECT current_version_id FROM papers WHERE id=?", (paper_id,)).fetchone()["current_version_id"]

        parser_run_id = "pr_test"
        repo.conn.execute(
            """
            INSERT INTO parser_runs(
                id, paper_id, version_id, parser_name, parser_version, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'test-parser', '0', 'done', 'now', 'now')
            """,
            (parser_run_id, paper_id, version_id),
        )
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            parser_run_id=parser_run_id,
            chunks=[
                {
                    "chunk_type": "paragraph",
                    "section_title": "Model Architecture",
                    "section_path": "Model Architecture / Attention",
                    "text": "Scaled dot-product attention text.",
                    "embedding_text": "Paper: Attention Is All You Need\nSection: Model Architecture / Attention\nType: paragraph\n\nContent:\nScaled dot-product attention text.",
                    "content_hash": "hash-1",
                    "source_block_ids": ["blk_1"],
                }
            ],
        )
        row = repo.conn.execute(
            """
            SELECT parser_run_id, chunk_type, section_path, embedding_text,
                   content_hash, source_block_ids_json
            FROM paper_chunks WHERE paper_id=?
            """,
            (paper_id,),
        ).fetchone()
        assert row["parser_run_id"] == parser_run_id
        assert row["chunk_type"] == "paragraph"
        assert row["section_path"] == "Model Architecture / Attention"
        assert row["embedding_text"].startswith("Paper: Attention Is All You Need")
        assert row["content_hash"] == "hash-1"
        assert row["source_block_ids_json"] == '["blk_1"]'

        await repo.aclose()

    asyncio.run(run())


def test_chunk_embedding_status_tracks_missing_and_current_hash(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()
        draft = PaperRecordDraft(title="Attention Is All You Need", year=2017, doi="10.5555/attention", source="test")
        paper_id = await repo.upsert_paper(draft, source_query="attention")
        version_id = repo.conn.execute("SELECT current_version_id FROM papers WHERE id=?", (paper_id,)).fetchone()["current_version_id"]
        parser_run_id = "pr_embedding_status"
        repo.conn.execute(
            """
            INSERT INTO parser_runs(
                id, paper_id, version_id, parser_name, parser_version, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'test-parser', '0', 'done', 'now', 'now')
            """,
            (parser_run_id, paper_id, version_id),
        )
        await repo.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            parser_run_id=parser_run_id,
            chunks=[
                {
                    "chunk_type": "paragraph",
                    "section_title": "Intro",
                    "text": "Chunk one.",
                    "embedding_text": "Chunk one.",
                    "content_hash": "hash-current",
                },
                {
                    "chunk_type": "paragraph",
                    "section_title": "Intro",
                    "text": "Chunk two.",
                    "embedding_text": "Chunk two.",
                    "content_hash": "hash-two",
                },
            ],
        )
        chunks = await repo.get_chunks_for_parser_run(parser_run_id)
        first = chunks[0]

        status_id = await repo.upsert_chunk_embedding_status(
            ChunkEmbeddingStatusDraft(
                chunk_id=first.chunk_id,
                paper_id=paper_id,
                parser_run_id=parser_run_id,
                content_hash=first.content_hash or "",
                embedding_provider_id="provider-a",
                embedding_model="model-a",
                embedding_dim=3,
                vector_backend="lancedb",
                vector_profile="provider-a:model-a",
                vector_table="chunk_embeddings",
                status="done",
            )
        )

        status = await repo.get_chunk_embedding_status(
            chunk_id=first.chunk_id,
            content_hash=first.content_hash or "",
            embedding_provider_id="provider-a",
            embedding_model="model-a",
            embedding_dim=3,
            vector_profile="provider-a:model-a",
        )
        assert status is not None
        assert status.id == status_id
        assert status.status == "done"

        missing = await repo.list_missing_or_stale_chunk_embeddings(
            paper_id=paper_id,
            embedding_provider_id="provider-a",
            embedding_model="model-a",
            embedding_dim=3,
            vector_profile="provider-a:model-a",
        )
        assert [item.chunk_index for item in missing] == [1]

        summary = await repo.summarize_chunk_embedding_status(
            paper_id=paper_id,
            embedding_provider_id="provider-a",
            embedding_model="model-a",
            embedding_dim=3,
            vector_profile="provider-a:model-a",
        )
        assert summary.total_chunks == 2
        assert summary.status_counts == {"done": 1, "missing": 1}
        assert summary.missing_count == 1
        assert summary.stale_count == 0

        repo.conn.execute(
            "UPDATE paper_chunks SET content_hash = ? WHERE id = ?",
            ("hash-new", first.chunk_id),
        )
        stale_summary = await repo.summarize_chunk_embedding_status(
            paper_id=paper_id,
            embedding_provider_id="provider-a",
            embedding_model="model-a",
            embedding_dim=3,
            vector_profile="provider-a:model-a",
        )
        assert stale_summary.missing_count == 2
        assert stale_summary.stale_count == 1
        await repo.aclose()

    asyncio.run(run())


def test_paths_create_only_used_index_directories(tmp_path):
    cfg = StorageConfig(root_dir=str(tmp_path / "paperos_data"))
    paths = PaperOSPaths.from_config(cfg, plugin_name="astrbot_plugin_paperos")
    paths.ensure_dirs()

    assert paths.database_path == paths.root_dir / "paperos.sqlite3"
    assert paths.object_dir == paths.root_dir / "objects"
    assert paths.index_dir == paths.root_dir / "indexes"
    assert paths.fts_index_dir == paths.root_dir / "indexes" / "fts"
    assert paths.vector_index_dir == paths.root_dir / "indexes" / "lancedb"
    assert paths.index_dir.is_dir()
    assert not paths.fts_index_dir.exists()
    assert not (paths.root_dir / "indexes" / "vector").exists()


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
            vector_index=LanceDBVectorIndex(paths.index_dir / "lancedb"),
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
                process_document=False,
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
