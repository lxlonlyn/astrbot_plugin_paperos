from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from paperos.search.models import FulltextLocation, FulltextStatus, PaperCandidate

from ..config import StorageConfig
from ..ids import new_id
from ..objects import StoredObject
from ..text import normalize_identifier, normalize_text


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLitePaperRepository:
    """SQLite implementation of the PaperOS local metadata store.

    The class intentionally keeps methods small and explicit. It is safe to use
    from async service code because operations are short; if ingestion becomes
    highly concurrent, move calls to asyncio.to_thread without changing schema.
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
        with self._conn:
            self._conn.executescript(sql)
            self._conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (1, "initial_storage_schema", utc_now()),
            )

    async def aclose(self) -> None:
        self._conn.close()

    # ---------------------------------------------------------------------
    # Paper identity / local dedup
    # ---------------------------------------------------------------------
    async def find_by_identifier(self, *, doi: str | None = None, arxiv_id: str | None = None) -> PaperCandidate | None:
        candidates: list[tuple[str, str]] = []
        if doi:
            candidates.append(("doi", normalize_identifier("doi", doi)))
        if arxiv_id:
            candidates.append(("arxiv", normalize_identifier("arxiv", arxiv_id)))
        for scheme, value in candidates:
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
                return self._row_to_candidate(row)
        return None

    async def search_by_title(self, title: str, *, limit: int = 10) -> list[PaperCandidate]:
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
        return [self._row_to_candidate(row) for row in rows]

    async def exists(self, candidate: PaperCandidate) -> bool:
        paper_id = await self.find_paper_id_for_candidate(candidate)
        return paper_id is not None

    async def find_paper_id_for_candidate(self, candidate: PaperCandidate) -> str | None:
        for scheme, value in self._candidate_identifiers(candidate):
            row = self._conn.execute(
                "SELECT paper_id FROM paper_identifiers WHERE scheme = ? AND value = ? LIMIT 1",
                (scheme, value),
            ).fetchone()
            if row:
                return str(row["paper_id"])

        title_norm = normalize_text(candidate.title)
        if title_norm:
            params: tuple[Any, ...]
            if candidate.year:
                params = (title_norm, candidate.year)
                row = self._conn.execute(
                    "SELECT id FROM papers WHERE title_norm = ? AND year = ? LIMIT 1",
                    params,
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT id FROM papers WHERE title_norm = ? LIMIT 1",
                    (title_norm,),
                ).fetchone()
            if row:
                return str(row["id"])
        return None

    async def upsert_candidate(
        self,
        candidate: PaperCandidate,
        *,
        source_query: str | None = None,
        decision: str = "search_selected",
        message: str | None = None,
    ) -> str:
        """Insert/update a searched paper and return paper_id."""

        now = utc_now()
        paper_id = await self.find_paper_id_for_candidate(candidate)
        title_norm = normalize_text(candidate.title)
        metadata = self._candidate_metadata(candidate)

        with self._conn:
            if paper_id is None:
                paper_id = new_id("p")
                self._conn.execute(
                    """
                    INSERT INTO papers(
                        id, canonical_title, title_norm, abstract, year, venue, publisher,
                        source, citation_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        paper_id,
                        candidate.title,
                        title_norm,
                        candidate.abstract,
                        candidate.year,
                        candidate.venue,
                        candidate.publisher,
                        candidate.source,
                        candidate.citation_count,
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
                        candidate.title,
                        title_norm,
                        candidate.abstract,
                        candidate.year,
                        candidate.venue,
                        candidate.publisher,
                        candidate.source,
                        candidate.citation_count,
                        now,
                        paper_id,
                    ),
                )

            self._upsert_alias(paper_id, candidate.title, "title", candidate.source, now)
            for scheme, value in self._candidate_identifiers(candidate):
                self._upsert_identifier(paper_id, scheme, value, candidate.source, now)

            version_id = new_id("pv")
            best_loc = self.best_fulltext_location(candidate)
            self._conn.execute(
                """
                INSERT INTO paper_versions(
                    id, paper_id, version_label, source, source_url, fulltext_status,
                    discovered_at, is_current, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    version_id,
                    paper_id,
                    best_loc.version if best_loc else None,
                    candidate.source,
                    (best_loc.url if best_loc else candidate.download_url or candidate.landing_url),
                    (best_loc.status.value if best_loc else None),
                    now,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            self._set_current_version(paper_id, version_id, now)
            self._upsert_fulltext_locations(paper_id, version_id, candidate.fulltext_locations, now)
            self._conn.execute(
                """
                INSERT INTO paper_ingest_events(
                    id, paper_id, source_query, decision, message, candidate_score,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("evt"),
                    paper_id,
                    source_query,
                    decision,
                    message,
                    candidate.score,
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
            self._conn.execute(
                "UPDATE paper_versions SET object_id = ? WHERE id = ?",
                (object_id, version_id),
            )
            self._conn.execute(
                """
                INSERT OR IGNORE INTO paper_object_links(paper_id, object_id, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (paper_id, object_id, role, now),
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
                    id, job_type, dedupe_key, paper_id, version_id, object_id, status,
                    priority, available_at, payload_json, created_at, updated_at
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
            self._conn.execute(
                "UPDATE paper_jobs SET status='done', finished_at=?, updated_at=? WHERE id=?",
                (now, now, job_id),
            )

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

    # ------------------------------------------------------------------
    # Chunks / FTS
    # ------------------------------------------------------------------
    async def replace_chunks(
        self,
        *,
        paper_id: str,
        version_id: str | None,
        object_id: str | None,
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
                section_title = chunk.get("section_title")
                self._conn.execute(
                    """
                    INSERT INTO paper_chunks(
                        id, paper_id, version_id, object_id, chunk_index, section_title,
                        page_start, page_end, text, token_count, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        paper_id,
                        version_id,
                        object_id,
                        int(chunk.get("chunk_index", i)),
                        section_title,
                        chunk.get("page_start"),
                        chunk.get("page_end"),
                        text,
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _candidate_identifiers(self, candidate: PaperCandidate) -> list[tuple[str, str]]:
        pairs = [
            ("doi", candidate.doi),
            ("arxiv", candidate.arxiv_id),
            ("core", candidate.core_id),
            ("openalex", candidate.openalex_id),
            ("semantic_scholar", candidate.semantic_scholar_id),
        ]
        out: list[tuple[str, str]] = []
        for scheme, value in pairs:
            norm = normalize_identifier(scheme, value)
            if norm:
                out.append((scheme, norm))
        return out

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
        self._conn.execute(
            "UPDATE papers SET current_version_id=?, updated_at=? WHERE id=?",
            (version_id, now, paper_id),
        )

    def _upsert_fulltext_locations(
        self,
        paper_id: str,
        version_id: str,
        locations: list[FulltextLocation],
        now: str,
    ) -> None:
        for loc in locations:
            self._conn.execute(
                """
                INSERT INTO fulltext_locations(
                    id, paper_id, version_id, url, source, kind, status, license, version,
                    host_type, confidence, reason, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id, url) DO UPDATE SET
                    version_id=excluded.version_id,
                    source=excluded.source,
                    kind=excluded.kind,
                    status=excluded.status,
                    license=excluded.license,
                    version=excluded.version,
                    host_type=excluded.host_type,
                    confidence=excluded.confidence,
                    reason=excluded.reason,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    new_id("ft"),
                    paper_id,
                    version_id,
                    loc.url,
                    loc.source,
                    loc.kind,
                    loc.status.value if hasattr(loc.status, "value") else str(loc.status),
                    loc.license,
                    loc.version,
                    loc.host_type,
                    loc.confidence,
                    loc.reason,
                    now,
                    now,
                ),
            )

    def best_fulltext_location(self, candidate: PaperCandidate) -> FulltextLocation | None:
        if not candidate.fulltext_locations:
            return None

        def key(loc: FulltextLocation) -> tuple[int, float]:
            status = loc.status.value if hasattr(loc.status, "value") else str(loc.status)
            status_rank = {
                FulltextStatus.VERIFIED_PDF.value: 100,
                FulltextStatus.HTML_FULLTEXT.value: 60,
                FulltextStatus.LANDING_ONLY.value: 20,
            }.get(status, 0)
            return (status_rank, loc.confidence or 0.0)

        return max(candidate.fulltext_locations, key=key)

    def _candidate_metadata(self, candidate: PaperCandidate) -> dict[str, Any]:
        data = self._safe_dataclass_dict(candidate)
        data["fulltext_locations"] = [self._safe_dataclass_dict(loc) for loc in candidate.fulltext_locations]
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

    def _row_to_candidate(self, row: sqlite3.Row) -> PaperCandidate:
        return PaperCandidate(
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
