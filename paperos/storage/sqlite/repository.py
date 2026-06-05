from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from ..config import StorageConfig
from ..ids import new_id
from ..interfaces import (
    ChunkEmbeddingStatusDraft,
    ChunkEmbeddingStatusRecord,
    ChunkEmbeddingStatusSummary,
)
from ..models import ChunkRecord, FulltextLocationRecord, PaperRecordDraft
from ..objects import StoredObject
from ..text import normalize_identifier, normalize_text
from ..document.grobid_models import NormalizedDocument


SCHEMA_VERSION = 1
SCHEMA_NAME = "initial_storage_schema"

KNOWN_SCHEMA_OBJECTS = [
    "index_status",
    "paper_chunks_fts",
    "chunk_embedding_status",
    "paper_chunks",
    "paper_references",
    "extracted_assets",
    "document_blocks",
    "document_sections",
    "parser_runs",
    "paper_jobs",
    "paper_ingest_events",
    "fulltext_locations",
    "paper_object_links",
    "paper_versions",
    "objects",
    "paper_aliases",
    "paper_identifiers",
    "papers",
    "schema_migrations",
]

REQUIRED_SCHEMA_COLUMNS = {
    "fulltext_locations": {
        "id",
        "paper_id",
        "version_id",
        "object_id",
        "url",
        "final_url",
        "source",
        "kind",
        "status",
        "license",
        "version",
        "host_type",
        "confidence",
        "reason",
        "filename",
        "sha256",
        "size_bytes",
        "content_type",
        "page_count",
        "first_seen_at",
        "last_seen_at",
    },
    "index_status": {
        "id",
        "paper_id",
        "index_name",
        "status",
        "profile",
        "updated_at",
        "message",
    },
    "parser_runs": {
        "id",
        "paper_id",
        "version_id",
        "object_id",
        "parser_name",
        "parser_version",
        "status",
        "raw_output_object_id",
        "normalized_object_id",
        "message",
        "created_at",
        "updated_at",
    },
    "document_sections": {
        "id",
        "paper_id",
        "parser_run_id",
        "parent_section_id",
        "title",
        "level",
        "order_index",
        "page_start",
        "page_end",
    },
    "document_blocks": {
        "id",
        "paper_id",
        "parser_run_id",
        "section_id",
        "block_index",
        "block_type",
        "text",
        "page_start",
        "page_end",
        "coords_json",
        "content_hash",
    },
    "extracted_assets": {
        "id",
        "paper_id",
        "parser_run_id",
        "asset_type",
        "label",
        "caption",
        "page",
        "coords_json",
        "object_id",
        "text_object_id",
        "linked_block_id",
        "metadata_json",
    },
    "paper_references": {
        "id",
        "paper_id",
        "parser_run_id",
        "ref_key",
        "raw_text",
        "title",
        "authors_json",
        "year",
        "venue",
        "doi",
        "arxiv_id",
        "resolved_paper_id",
        "confidence",
    },
    "paper_chunks": {
        "id",
        "paper_id",
        "version_id",
        "object_id",
        "parser_run_id",
        "chunk_index",
        "chunk_type",
        "section_title",
        "section_path",
        "page_start",
        "page_end",
        "text",
        "embedding_text",
        "content_hash",
        "source_block_ids_json",
        "prev_chunk_id",
        "next_chunk_id",
        "token_count",
        "metadata_json",
        "created_at",
    },
    "chunk_embedding_status": {
        "id",
        "chunk_id",
        "paper_id",
        "parser_run_id",
        "content_hash",
        "embedding_provider_id",
        "embedding_model",
        "embedding_dim",
        "vector_backend",
        "vector_profile",
        "vector_table",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLitePaperRepository:
    """SQLite implementation of the PaperOS local metadata store.

    This class is deliberately storage-facing. It does not import search DTOs and
    it never performs network I/O. Higher-level facades convert search results to
    PaperRecordDraft before calling this repository.
    """

    def __init__(self, db_path: Path, cfg: StorageConfig | None = None):
        self.db_path = Path(db_path)
        self.cfg = cfg or StorageConfig()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.db_path,
            timeout=self.cfg.sqlite_timeout_seconds,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def _configure_connection(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute(f"PRAGMA busy_timeout = {int(self.cfg.sqlite_busy_timeout_ms)}")
        self._conn.execute(f"PRAGMA journal_mode = {self.cfg.sqlite_journal_mode}")
        self._conn.execute(f"PRAGMA synchronous = {self.cfg.sqlite_synchronous}")

    async def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        sql = schema_path.read_text(encoding="utf-8")
        if not self._schema_is_current():
            self._reset_schema()
        with self._conn:
            self._conn.executescript(sql)
            self._conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (SCHEMA_VERSION, SCHEMA_NAME, utc_now()),
            )

    async def aclose(self) -> None:
        self._conn.close()

    def _schema_is_current(self) -> bool:
        existing = self._existing_schema_objects()
        if not existing:
            return True

        for table_name, required_columns in REQUIRED_SCHEMA_COLUMNS.items():
            if table_name not in existing:
                return False
            if not required_columns.issubset(self._table_columns(table_name)):
                return False
        return True

    def _existing_schema_objects(self) -> set[str]:
        rows = self._conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return {str(row["name"]) for row in rows}

    def _table_columns(self, table_name: str) -> set[str]:
        rows = self._conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _reset_schema(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = OFF")
        try:
            with self._conn:
                for object_name in KNOWN_SCHEMA_OBJECTS:
                    self._conn.execute(f"DROP TABLE IF EXISTS {object_name}")
        finally:
            self._conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------------
    # Paper identity / local dedup
    # ------------------------------------------------------------------

    async def find_by_identifier(self, *, doi: str | None = None, arxiv_id: str | None = None) -> PaperRecordDraft | None:
        pairs: list[tuple[str, str | None]] = [("doi", doi), ("arxiv", arxiv_id)]
        for scheme, raw_value in pairs:
            value = normalize_identifier(scheme, raw_value)
            if not value:
                continue
            row = self._conn.execute(
                """
                SELECT p.* FROM papers p
                JOIN paper_identifiers i ON i.paper_id = p.id
                WHERE i.scheme = ? AND i.value = ?
                LIMIT 1
                """,
                (scheme, value),
            ).fetchone()
            if row:
                return self._row_to_draft(row)
        return None

    async def search_by_title(self, title: str, *, limit: int = 10) -> list[PaperRecordDraft]:
        title_norm = normalize_text(title)
        if not title_norm:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM papers
            WHERE title_norm = ? OR title_norm LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (title_norm, f"%{title_norm}%", limit),
        ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    async def exists(self, draft: PaperRecordDraft) -> bool:
        return await self.find_paper_id_for_draft(draft) is not None

    async def find_paper_id_for_draft(self, draft: PaperRecordDraft) -> str | None:
        for scheme, value in self._draft_identifiers(draft):
            row = self._conn.execute(
                "SELECT paper_id FROM paper_identifiers WHERE scheme = ? AND value = ? LIMIT 1",
                (scheme, value),
            ).fetchone()
            if row:
                return str(row["paper_id"])

        title_norm = normalize_text(draft.title)
        if not title_norm:
            return None
        if draft.year:
            row = self._conn.execute(
                "SELECT id FROM papers WHERE title_norm = ? AND year = ? LIMIT 1",
                (title_norm, draft.year),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT id FROM papers WHERE title_norm = ? LIMIT 1",
                (title_norm,),
            ).fetchone()
        return str(row["id"]) if row else None

    async def upsert_paper(
        self,
        draft: PaperRecordDraft,
        *,
        source_query: str | None = None,
        decision: str = "search_selected",
        message: str | None = None,
    ) -> str:
        """Insert/update a paper draft and return paper_id."""

        now = utc_now()
        paper_id = await self.find_paper_id_for_draft(draft)
        title_norm = normalize_text(draft.title)
        metadata = self._draft_metadata(draft)

        with self._conn:
            if paper_id is None:
                paper_id = new_id("p")
                self._conn.execute(
                    """
                    INSERT INTO papers(
                        id, canonical_title, title_norm, abstract, year, venue,
                        publisher, source, citation_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        paper_id,
                        draft.title,
                        title_norm,
                        draft.abstract,
                        draft.year,
                        draft.venue,
                        draft.publisher,
                        draft.source,
                        draft.citation_count,
                        now,
                        now,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE papers SET
                        canonical_title = COALESCE(NULLIF(?, ''), canonical_title),
                        title_norm = COALESCE(NULLIF(?, ''), title_norm),
                        abstract = COALESCE(?, abstract),
                        year = COALESCE(?, year),
                        venue = COALESCE(?, venue),
                        publisher = COALESCE(?, publisher),
                        source = COALESCE(?, source),
                        citation_count = COALESCE(?, citation_count),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        draft.title,
                        title_norm,
                        draft.abstract,
                        draft.year,
                        draft.venue,
                        draft.publisher,
                        draft.source,
                        draft.citation_count,
                        now,
                        paper_id,
                    ),
                )

            self._upsert_alias(paper_id, draft.title, "title", draft.source, now)
            for scheme, value in self._draft_identifiers(draft):
                self._upsert_identifier(paper_id, scheme, value, draft.source, now)

            version_id = new_id("pv")
            best_loc = self.best_fulltext_location(draft)
            self._conn.execute(
                """
                INSERT INTO paper_versions(
                    id, paper_id, version_label, source, source_url,
                    fulltext_status, discovered_at, is_current, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    version_id,
                    paper_id,
                    best_loc.version if best_loc else None,
                    draft.source,
                    (best_loc.url if best_loc else draft.landing_url),
                    (best_loc.status if best_loc else None),
                    now,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            self._set_current_version(paper_id, version_id, now)
            self._upsert_fulltext_locations(paper_id, version_id, draft.fulltext_locations, now)
            self._conn.execute(
                """
                INSERT INTO paper_ingest_events(
                    id, paper_id, source_query, decision, message,
                    candidate_score, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("evt"),
                    paper_id,
                    source_query,
                    decision,
                    message,
                    draft.score,
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                ),
            )
        return paper_id

    # ------------------------------------------------------------------
    # Objects / versions
    # ------------------------------------------------------------------

    async def register_object(self, stored: StoredObject) -> str:
        now = utc_now()
        with self._conn:
            existing = self._conn.execute(
                "SELECT id FROM objects WHERE storage_key = ? LIMIT 1",
                (stored.storage_key,),
            ).fetchone()
            if existing:
                return str(existing["id"])
            self._conn.execute(
                """
                INSERT INTO objects(id, kind, storage_key, sha256, size_bytes, mime_type, suffix, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.id,
                    stored.kind,
                    stored.storage_key,
                    stored.sha256,
                    stored.size_bytes,
                    stored.mime_type,
                    stored.suffix,
                    now,
                ),
            )
        return stored.id

    async def attach_object_to_current_version(self, *, paper_id: str, object_id: str, role: str = "pdf") -> None:
        now = utc_now()
        with self._conn:
            row = self._conn.execute(
                "SELECT current_version_id FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()
            if not row or not row["current_version_id"]:
                raise ValueError(f"paper has no current version: {paper_id}")
            version_id = str(row["current_version_id"])
            self._conn.execute("UPDATE paper_versions SET object_id = ? WHERE id = ?", (object_id, version_id))
            self._conn.execute(
                """
                INSERT OR IGNORE INTO paper_object_links(paper_id, object_id, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (paper_id, object_id, role, now),
            )

    async def attach_object_to_fulltext_location(
        self,
        *,
        paper_id: str,
        url: str,
        object_id: str,
    ) -> None:
        now = utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE fulltext_locations
                SET object_id = ?, last_seen_at = ?
                WHERE paper_id = ? AND url = ?
                """,
                (object_id, now, paper_id, url),
            )

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    async def enqueue_job(
        self,
        job_type: str,
        *,
        dedupe_key: str | None = None,
        paper_id: str | None = None,
        version_id: str | None = None,
        object_id: str | None = None,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        available_at: str | None = None,
    ) -> str:
        now = utc_now()
        job_id = new_id("job")
        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO paper_jobs(
                    id, job_type, dedupe_key, paper_id, version_id, object_id,
                    status, priority, available_at, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job_type,
                    dedupe_key,
                    paper_id,
                    version_id,
                    object_id,
                    priority,
                    available_at or now,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            if dedupe_key:
                row = self._conn.execute(
                    "SELECT id FROM paper_jobs WHERE job_type = ? AND dedupe_key = ?",
                    (job_type, dedupe_key),
                ).fetchone()
                return str(row["id"])
        return job_id

    async def claim_next_job(self, *, worker_id: str, stale_after_seconds: int = 600) -> dict[str, Any] | None:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="seconds")
        stale_before = (now_dt - timedelta(seconds=stale_after_seconds)).isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                UPDATE paper_jobs
                SET status='pending', locked_by=NULL, locked_at=NULL, heartbeat_at=NULL, updated_at=?
                WHERE status='running' AND locked_at IS NOT NULL AND locked_at < ?
                """,
                (now, stale_before),
            )
            row = self._conn.execute(
                """
                SELECT * FROM paper_jobs
                WHERE status='pending' AND available_at <= ? AND attempts < max_attempts
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                return None
            self._conn.execute(
                """
                UPDATE paper_jobs
                SET status='running', locked_by=?, locked_at=?, heartbeat_at=?,
                    started_at=COALESCE(started_at, ?), attempts=attempts+1, updated_at=?
                WHERE id=?
                """,
                (worker_id, now, now, now, now, row["id"]),
            )
            claimed = self._conn.execute("SELECT * FROM paper_jobs WHERE id=?", (row["id"],)).fetchone()
        return self._job_to_dict(claimed) if claimed else None

    async def mark_job_done(self, job_id: str) -> None:
        now = utc_now()
        with self._conn:
            self._conn.execute("UPDATE paper_jobs SET status='done', finished_at=?, updated_at=? WHERE id=?", (now, now, job_id))

    async def mark_job_failed(self, job_id: str, error_message: str) -> None:
        now = utc_now()
        with self._conn:
            row = self._conn.execute("SELECT attempts, max_attempts FROM paper_jobs WHERE id=?", (job_id,)).fetchone()
            status = "failed"
            if row and int(row["attempts"]) < int(row["max_attempts"]):
                status = "pending"
            self._conn.execute(
                """
                UPDATE paper_jobs
                SET status=?, error_message=?, locked_by=NULL, locked_at=NULL,
                    heartbeat_at=NULL, updated_at=?
                WHERE id=?
                """,
                (status, error_message[:2000], now, job_id),
            )

    async def mark_job_failed_final(self, job_id: str, error_message: str) -> None:
        now = utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE paper_jobs
                SET status='failed', error_message=?, locked_by=NULL, locked_at=NULL,
                    heartbeat_at=NULL, finished_at=?, updated_at=?
                WHERE id=?
                """,
                (error_message[:2000], now, now, job_id),
            )

    # ------------------------------------------------------------------
    # Document processing
    # ------------------------------------------------------------------

    async def persist_document_processing_result(
        self,
        *,
        paper_id: str,
        version_id: str | None,
        object_id: str,
        parser_name: str,
        parser_version: str | None,
        raw_output_object_id: str | None,
        normalized_object_id: str | None,
        document: NormalizedDocument,
        chunks: Iterable[dict[str, Any]],
        message: str | None = None,
    ) -> str:
        now = utc_now()
        parser_run_id = new_id("pr")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO parser_runs(
                    id, paper_id, version_id, object_id, parser_name, parser_version,
                    status, raw_output_object_id, normalized_object_id, message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'done', ?, ?, ?, ?, ?)
                """,
                (
                    parser_run_id,
                    paper_id,
                    version_id,
                    object_id,
                    parser_name,
                    parser_version,
                    raw_output_object_id,
                    normalized_object_id,
                    message,
                    now,
                    now,
                ),
            )
            section_ids: dict[int, str] = {}
            for idx, section in enumerate(document.sections):
                section_id = new_id("sec")
                section_ids[idx] = section_id
                parent_id = section_ids.get(section.parent_index) if section.parent_index is not None else None
                self._conn.execute(
                    """
                    INSERT INTO document_sections(
                        id, paper_id, parser_run_id, parent_section_id, title,
                        level, order_index, page_start, page_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section_id,
                        paper_id,
                        parser_run_id,
                        parent_id,
                        section.title,
                        section.level,
                        section.order_index,
                        section.page_start,
                        section.page_end,
                    ),
                )
            block_ids: dict[int, str] = {}
            for block in document.blocks:
                block_id = new_id("blk")
                block_ids[block.block_index] = block_id
                section_id = section_ids.get(block.section_index) if block.section_index is not None else None
                self._conn.execute(
                    """
                    INSERT INTO document_blocks(
                        id, paper_id, parser_run_id, section_id, block_index,
                        block_type, text, page_start, page_end, coords_json,
                        content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        block_id,
                        paper_id,
                        parser_run_id,
                        section_id,
                        block.block_index,
                        block.block_type,
                        block.text,
                        block.page_start,
                        block.page_end,
                        json.dumps(block.coords or {}, ensure_ascii=False),
                        block.content_hash,
                    ),
                )
            for ref in document.references:
                self._conn.execute(
                    """
                    INSERT INTO paper_references(
                        id, paper_id, parser_run_id, ref_key, raw_text, title,
                        authors_json, year, venue, doi, arxiv_id, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("ref"),
                        paper_id,
                        parser_run_id,
                        ref.ref_key,
                        ref.raw_text,
                        ref.title,
                        json.dumps(ref.authors, ensure_ascii=False),
                        ref.year,
                        ref.venue,
                        ref.doi,
                        ref.arxiv_id,
                        ref.confidence,
                    ),
                )

        await self.replace_chunks(
            paper_id=paper_id,
            version_id=version_id,
            object_id=object_id,
            parser_run_id=parser_run_id,
            chunks=chunks,
        )
        return parser_run_id

    async def current_version_id(self, paper_id: str) -> str | None:
        row = self._conn.execute("SELECT current_version_id FROM papers WHERE id=?", (paper_id,)).fetchone()
        return str(row["current_version_id"]) if row and row["current_version_id"] else None

    # ------------------------------------------------------------------
    # Chunks / FTS
    # ------------------------------------------------------------------

    async def replace_chunks(
        self,
        *,
        paper_id: str,
        version_id: str | None,
        object_id: str | None,
        parser_run_id: str | None = None,
        chunks: Iterable[dict[str, Any]],
    ) -> None:
        now = utc_now()
        title_row = self._conn.execute("SELECT canonical_title FROM papers WHERE id=?", (paper_id,)).fetchone()
        title = str(title_row["canonical_title"]) if title_row else ""
        with self._conn:
            existing = self._conn.execute("SELECT id FROM paper_chunks WHERE paper_id=?", (paper_id,)).fetchall()
            existing_ids = [str(row["id"]) for row in existing]
            if existing_ids:
                self._conn.executemany("DELETE FROM paper_chunks_fts WHERE chunk_id=?", [(cid,) for cid in existing_ids])
            self._conn.execute("DELETE FROM paper_chunks WHERE paper_id=?", (paper_id,))
            for i, chunk in enumerate(chunks):
                chunk_id = new_id("chk")
                text = str(chunk.get("text", ""))
                embedding_text = chunk.get("embedding_text") or text
                section_title = chunk.get("section_title")
                source_block_ids = chunk.get("source_block_ids", chunk.get("source_block_ids_json", []))
                self._conn.execute(
                    """
                    INSERT INTO paper_chunks(
                        id, paper_id, version_id, object_id, parser_run_id,
                        chunk_index, chunk_type, section_title, section_path,
                        page_start, page_end, text, embedding_text, content_hash,
                        source_block_ids_json, prev_chunk_id, next_chunk_id,
                        token_count, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        paper_id,
                        version_id,
                        object_id,
                        chunk.get("parser_run_id", parser_run_id),
                        int(chunk.get("chunk_index", i)),
                        chunk.get("chunk_type", "paragraph"),
                        section_title,
                        chunk.get("section_path"),
                        chunk.get("page_start"),
                        chunk.get("page_end"),
                        text,
                        embedding_text,
                        chunk.get("content_hash"),
                        json.dumps(source_block_ids or [], ensure_ascii=False),
                        chunk.get("prev_chunk_id"),
                        chunk.get("next_chunk_id"),
                        chunk.get("token_count"),
                        json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                        now,
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO paper_chunks_fts(chunk_id, paper_id, title, section_title, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (chunk_id, paper_id, title, section_title, text),
                )

    async def search_chunks_fts(
        self,
        query: str,
        *,
        paper_id: str | None = None,
        limit: int = 20,
    ) -> list[ChunkRecord]:
        match_query = self._fts_match_query(query)
        if not match_query:
            return []
        limit = max(1, min(int(limit), 100))
        rows = self._conn.execute(
            """
            SELECT
                c.*,
                p.canonical_title AS paper_title,
                bm25(paper_chunks_fts) AS fts_rank
            FROM paper_chunks_fts
            JOIN paper_chunks c ON c.id = paper_chunks_fts.chunk_id
            JOIN papers p ON p.id = c.paper_id
            WHERE paper_chunks_fts MATCH ?
              AND (? IS NULL OR c.paper_id = ?)
            ORDER BY bm25(paper_chunks_fts), c.paper_id, c.chunk_index
            LIMIT ?
            """,
            (match_query, paper_id, paper_id, limit),
        ).fetchall()
        return [
            self._chunk_row_to_record(row, rank=idx + 1, score=self._fts_score(row["fts_rank"]))
            for idx, row in enumerate(rows)
        ]

    async def get_chunks_by_ids(self, ids: list[str]) -> list[ChunkRecord]:
        ids = [str(item) for item in ids if str(item)]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"""
            SELECT c.*, p.canonical_title AS paper_title
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.id IN ({placeholders})
            """,
            tuple(ids),
        ).fetchall()
        by_id = {str(row["id"]): self._chunk_row_to_record(row) for row in rows}
        return [by_id[item] for item in ids if item in by_id]

    async def get_neighbor_chunks(
        self,
        chunk_id: str,
        *,
        before: int = 1,
        after: int = 1,
    ) -> list[ChunkRecord]:
        row = self._conn.execute(
            """
            SELECT paper_id, version_id, chunk_index
            FROM paper_chunks
            WHERE id = ?
            """,
            (chunk_id,),
        ).fetchone()
        if not row:
            return []
        before = max(0, min(int(before), 10))
        after = max(0, min(int(after), 10))
        start = int(row["chunk_index"]) - before
        end = int(row["chunk_index"]) + after
        rows = self._conn.execute(
            """
            SELECT c.*, p.canonical_title AS paper_title
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.paper_id = ?
              AND (
                (? IS NULL AND c.version_id IS NULL)
                OR c.version_id = ?
              )
              AND c.chunk_index BETWEEN ? AND ?
            ORDER BY c.chunk_index
            """,
            (row["paper_id"], row["version_id"], row["version_id"], start, end),
        ).fetchall()
        return [self._chunk_row_to_record(item) for item in rows]

    async def get_paper_citation_metadata(self, paper_id: str) -> dict[str, Any]:
        paper = self._conn.execute(
            """
            SELECT id, canonical_title, year, venue, publisher, current_version_id
            FROM papers
            WHERE id = ?
            """,
            (paper_id,),
        ).fetchone()
        if not paper:
            return {}
        identifiers = self._conn.execute(
            """
            SELECT scheme, value
            FROM paper_identifiers
            WHERE paper_id = ?
            ORDER BY scheme, value
            """,
            (paper_id,),
        ).fetchall()
        return {
            "paper_id": str(paper["id"]),
            "title": str(paper["canonical_title"]),
            "year": paper["year"],
            "venue": paper["venue"],
            "publisher": paper["publisher"],
            "current_version_id": paper["current_version_id"],
            "identifiers": {str(row["scheme"]): str(row["value"]) for row in identifiers},
        }

    async def get_chunks_for_parser_run(self, parser_run_id: str) -> list[ChunkRecord]:
        rows = self._conn.execute(
            """
            SELECT c.*, p.canonical_title AS paper_title
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.parser_run_id = ?
            ORDER BY c.paper_id, c.chunk_index
            """,
            (parser_run_id,),
        ).fetchall()
        return [self._chunk_row_to_record(row) for row in rows]

    async def get_chunks_for_paper(self, paper_id: str) -> list[ChunkRecord]:
        rows = self._conn.execute(
            """
            SELECT c.*, p.canonical_title AS paper_title
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.paper_id = ?
            ORDER BY c.chunk_index
            """,
            (paper_id,),
        ).fetchall()
        return [self._chunk_row_to_record(row) for row in rows]

    async def update_index_status(
        self,
        *,
        paper_id: str,
        index_name: str,
        status: str,
        profile: str | None = None,
        message: str | None = None,
    ) -> None:
        now = utc_now()
        profile_value = profile or ""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO index_status(id, paper_id, index_name, status, profile, updated_at, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id, index_name, profile) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    message = excluded.message
                """,
                (new_id("idx"), paper_id, index_name, status, profile_value, now, message),
            )

    async def get_chunk_embedding_status(
        self,
        *,
        chunk_id: str,
        content_hash: str,
        embedding_provider_id: str,
        embedding_model: str,
        embedding_dim: int,
        vector_profile: str,
    ) -> ChunkEmbeddingStatusRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM chunk_embedding_status
            WHERE chunk_id = ?
              AND content_hash = ?
              AND embedding_provider_id = ?
              AND embedding_model = ?
              AND embedding_dim = ?
              AND vector_profile = ?
            """,
            (
                chunk_id,
                content_hash,
                embedding_provider_id,
                embedding_model,
                embedding_dim,
                vector_profile,
            ),
        ).fetchone()
        return self._embedding_status_row_to_record(row) if row else None

    async def upsert_chunk_embedding_status(self, draft: ChunkEmbeddingStatusDraft) -> str:
        now = utc_now()
        existing = self._conn.execute(
            """
            SELECT id, created_at
            FROM chunk_embedding_status
            WHERE chunk_id = ?
              AND content_hash = ?
              AND embedding_provider_id = ?
              AND embedding_model = ?
              AND embedding_dim = ?
              AND vector_profile = ?
            """,
            (
                draft.chunk_id,
                draft.content_hash,
                draft.embedding_provider_id,
                draft.embedding_model,
                draft.embedding_dim,
                draft.vector_profile,
            ),
        ).fetchone()
        status_id = str(existing["id"]) if existing else new_id("emb")
        created_at = str(existing["created_at"]) if existing else now
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO chunk_embedding_status(
                    id, chunk_id, paper_id, parser_run_id, content_hash,
                    embedding_provider_id, embedding_model, embedding_dim,
                    vector_backend, vector_profile, vector_table, status,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    chunk_id, content_hash, embedding_provider_id, embedding_model,
                    embedding_dim, vector_profile
                ) DO UPDATE SET
                    paper_id = excluded.paper_id,
                    parser_run_id = excluded.parser_run_id,
                    vector_backend = excluded.vector_backend,
                    vector_table = excluded.vector_table,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    status_id,
                    draft.chunk_id,
                    draft.paper_id,
                    draft.parser_run_id,
                    draft.content_hash,
                    draft.embedding_provider_id,
                    draft.embedding_model,
                    draft.embedding_dim,
                    draft.vector_backend,
                    draft.vector_profile,
                    draft.vector_table,
                    draft.status,
                    draft.error_message,
                    created_at,
                    now,
                ),
            )
        return status_id

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
    ) -> list[ChunkRecord]:
        filters: list[str] = []
        params: list[Any] = [
            embedding_provider_id,
            embedding_model,
            embedding_dim,
            vector_profile,
        ]
        if paper_id:
            filters.append("c.paper_id = ?")
            params.append(paper_id)
        if parser_run_id:
            filters.append("c.parser_run_id = ?")
            params.append(parser_run_id)
        where = (" AND " + " AND ".join(filters)) if filters else ""
        params.append(max(1, int(limit)))
        rows = self._conn.execute(
            f"""
            SELECT c.*, p.canonical_title AS paper_title
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            LEFT JOIN chunk_embedding_status s
              ON s.chunk_id = c.id
             AND s.content_hash = c.content_hash
             AND s.embedding_provider_id = ?
             AND s.embedding_model = ?
             AND s.embedding_dim = ?
             AND s.vector_profile = ?
            WHERE s.id IS NULL{where}
            ORDER BY c.paper_id, c.chunk_index
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [self._chunk_row_to_record(row) for row in rows]

    async def summarize_chunk_embedding_status(
        self,
        *,
        paper_id: str,
        embedding_provider_id: str | None = None,
        embedding_model: str | None = None,
        embedding_dim: int | None = None,
        vector_profile: str | None = None,
    ) -> ChunkEmbeddingStatusSummary:
        total_chunks = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM paper_chunks WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()[0]
        )

        join_filters = ["s.chunk_id = c.id", "s.content_hash = c.content_hash"]
        params: list[Any] = []
        if embedding_provider_id is not None:
            join_filters.append("s.embedding_provider_id = ?")
            params.append(embedding_provider_id)
        if embedding_model is not None:
            join_filters.append("s.embedding_model = ?")
            params.append(embedding_model)
        if embedding_dim is not None:
            join_filters.append("s.embedding_dim = ?")
            params.append(embedding_dim)
        if vector_profile is not None:
            join_filters.append("s.vector_profile = ?")
            params.append(vector_profile)

        rows = self._conn.execute(
            f"""
            SELECT COALESCE(s.status, 'missing') AS status, COUNT(*) AS count
            FROM paper_chunks c
            LEFT JOIN chunk_embedding_status s
              ON {" AND ".join(join_filters)}
            WHERE c.paper_id = ?
            GROUP BY COALESCE(s.status, 'missing')
            """,
            tuple([*params, paper_id]),
        ).fetchall()
        status_counts = {str(row["status"]): int(row["count"]) for row in rows}

        stale_filters = ["s.chunk_id = c.id", "s.content_hash <> c.content_hash"]
        stale_params: list[Any] = []
        if embedding_provider_id is not None:
            stale_filters.append("s.embedding_provider_id = ?")
            stale_params.append(embedding_provider_id)
        if embedding_model is not None:
            stale_filters.append("s.embedding_model = ?")
            stale_params.append(embedding_model)
        if embedding_dim is not None:
            stale_filters.append("s.embedding_dim = ?")
            stale_params.append(embedding_dim)
        if vector_profile is not None:
            stale_filters.append("s.vector_profile = ?")
            stale_params.append(vector_profile)
        stale_count = int(
            self._conn.execute(
                f"""
                SELECT COUNT(DISTINCT c.id)
                FROM paper_chunks c
                JOIN chunk_embedding_status s ON {" AND ".join(stale_filters)}
                WHERE c.paper_id = ?
                """,
                tuple([*stale_params, paper_id]),
            ).fetchone()[0]
        )
        return ChunkEmbeddingStatusSummary(
            total_chunks=total_chunks,
            status_counts=status_counts,
            missing_count=status_counts.get("missing", 0),
            stale_count=stale_count,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _draft_identifiers(self, draft: PaperRecordDraft) -> list[tuple[str, str]]:
        pairs = [
            ("doi", draft.doi),
            ("arxiv", draft.arxiv_id),
            ("core", draft.core_id),
            ("openalex", draft.openalex_id),
            ("semantic_scholar", draft.semantic_scholar_id),
        ]
        out: list[tuple[str, str]] = []
        for scheme, value in pairs:
            norm = normalize_identifier(scheme, value)
            if norm:
                out.append((scheme, norm))
        return out

    def _fts_match_query(self, query: str) -> str:
        tokens = re.findall(r"[\w]+", query or "", flags=re.UNICODE)
        tokens = [token for token in tokens if token.strip()]
        if not tokens:
            return ""
        return " OR ".join(f'"{token.replace(chr(34), chr(34) + chr(34))}"' for token in tokens[:12])

    def _fts_score(self, rank_value: object) -> float:
        try:
            rank = float(rank_value)
        except (TypeError, ValueError):
            return 0.0
        # FTS5 bm25 is lower-is-better and commonly negative. Convert it into a
        # positive sorting hint without pretending it is a calibrated relevance.
        return -rank

    def _chunk_row_to_record(
        self,
        row: sqlite3.Row,
        *,
        rank: int | None = None,
        score: float = 0.0,
    ) -> ChunkRecord:
        metadata: dict[str, Any]
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        return ChunkRecord(
            chunk_id=str(row["id"]),
            paper_id=str(row["paper_id"]),
            version_id=row["version_id"],
            object_id=row["object_id"],
            parser_run_id=row["parser_run_id"],
            title=str(row["paper_title"]),
            chunk_index=int(row["chunk_index"]),
            text=str(row["text"]),
            embedding_text=row["embedding_text"],
            content_hash=row["content_hash"],
            section_title=row["section_title"],
            section_path=row["section_path"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            chunk_type=str(row["chunk_type"] or "paragraph"),
            token_count=row["token_count"],
            score=score,
            rank=rank,
            metadata=metadata,
        )

    def _embedding_status_row_to_record(self, row: sqlite3.Row) -> ChunkEmbeddingStatusRecord:
        return ChunkEmbeddingStatusRecord(
            id=str(row["id"]),
            chunk_id=str(row["chunk_id"]),
            paper_id=str(row["paper_id"]),
            parser_run_id=row["parser_run_id"],
            content_hash=str(row["content_hash"]),
            embedding_provider_id=str(row["embedding_provider_id"]),
            embedding_model=str(row["embedding_model"]),
            embedding_dim=int(row["embedding_dim"]),
            vector_backend=str(row["vector_backend"]),
            vector_profile=str(row["vector_profile"]),
            vector_table=str(row["vector_table"]),
            status=str(row["status"]),
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _upsert_identifier(self, paper_id: str, scheme: str, value: str, source: str | None, now: str) -> None:
        self._conn.execute(
            """
            INSERT INTO paper_identifiers(paper_id, scheme, value, source, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(scheme, value) DO UPDATE SET
                paper_id=excluded.paper_id,
                source=COALESCE(excluded.source, paper_identifiers.source),
                last_seen_at=excluded.last_seen_at
            """,
            (paper_id, scheme, value, source, now, now),
        )

    def _upsert_alias(self, paper_id: str, alias: str | None, alias_type: str, source: str | None, now: str) -> None:
        alias_norm = normalize_text(alias)
        if not alias or not alias_norm:
            return
        self._conn.execute(
            """
            INSERT OR IGNORE INTO paper_aliases(id, paper_id, alias, alias_norm, alias_type, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id("alias"), paper_id, alias, alias_norm, alias_type, source, now),
        )

    def _set_current_version(self, paper_id: str, version_id: str, now: str) -> None:
        self._conn.execute("UPDATE paper_versions SET is_current=0 WHERE paper_id=?", (paper_id,))
        self._conn.execute("UPDATE paper_versions SET is_current=1 WHERE id=?", (version_id,))
        self._conn.execute("UPDATE papers SET current_version_id=?, updated_at=? WHERE id=?", (version_id, now, paper_id))

    def _upsert_fulltext_locations(
        self,
        paper_id: str,
        version_id: str,
        locations: list[FulltextLocationRecord],
        now: str,
    ) -> None:
        for loc in locations:
            self._conn.execute(
                """
                INSERT INTO fulltext_locations(
                    id, paper_id, version_id, url, final_url, source, kind, status,
                    license, version, host_type, confidence, reason, filename,
                    sha256, size_bytes, content_type, page_count,
                    first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id, url) DO UPDATE SET
                    version_id=excluded.version_id,
                    final_url=excluded.final_url,
                    source=excluded.source,
                    kind=excluded.kind,
                    status=excluded.status,
                    license=excluded.license,
                    version=excluded.version,
                    host_type=excluded.host_type,
                    confidence=excluded.confidence,
                    reason=excluded.reason,
                    filename=excluded.filename,
                    sha256=excluded.sha256,
                    size_bytes=excluded.size_bytes,
                    content_type=excluded.content_type,
                    page_count=excluded.page_count,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    new_id("ft"),
                    paper_id,
                    version_id,
                    loc.url,
                    loc.final_url,
                    loc.source,
                    loc.kind,
                    loc.status,
                    loc.license,
                    loc.version,
                    loc.host_type,
                    loc.confidence,
                    loc.reason,
                    loc.filename,
                    loc.sha256,
                    loc.size_bytes,
                    loc.content_type,
                    loc.page_count,
                    now,
                    now,
                ),
            )

    def best_fulltext_location(self, draft: PaperRecordDraft) -> FulltextLocationRecord | None:
        if not draft.fulltext_locations:
            return None

        def key(loc: FulltextLocationRecord) -> tuple[int, float]:
            status_rank = {"verified_pdf": 100, "html_fulltext": 60, "landing_only": 20}.get(loc.status, 0)
            return (status_rank, loc.confidence or 0.0)

        return max(draft.fulltext_locations, key=key)

    def _draft_metadata(self, draft: PaperRecordDraft) -> dict[str, Any]:
        data = self._safe_dataclass_dict(draft)
        data["fulltext_locations"] = [self._safe_dataclass_dict(loc) for loc in draft.fulltext_locations]
        return data

    def _safe_dataclass_dict(self, value: Any) -> dict[str, Any]:
        if is_dataclass(value):
            data = asdict(value)
        elif isinstance(value, dict):
            data = dict(value)
        else:
            data = {}
        return self._jsonable(data)

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._jsonable(v) for v in value]
        if hasattr(value, "value"):
            return value.value
        return value

    def _row_to_draft(self, row: sqlite3.Row) -> PaperRecordDraft:
        return PaperRecordDraft(
            title=str(row["canonical_title"]),
            year=row["year"],
            venue=row["venue"],
            publisher=row["publisher"],
            abstract=row["abstract"],
            citation_count=row["citation_count"],
            source=row["source"] or "local",
        )

    def _job_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            data["payload"] = json.loads(data.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            data["payload"] = {}
        return data
