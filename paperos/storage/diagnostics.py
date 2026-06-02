from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .factory import PaperOSStorageContext
from .text import normalize_identifier, normalize_text


@dataclass(frozen=True)
class StorageCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class StorageStats:
    papers: int | None = None
    objects: int | None = None
    pdf_objects: int | None = None
    fulltext_locations: int | None = None
    chunks: int | None = None
    jobs_by_status: dict[str, int] = field(default_factory=dict)
    objects_size_bytes: int | None = None
    sqlite_size_bytes: int | None = None
    indexes_size_bytes: int | None = None


@dataclass(frozen=True)
class StorageStatus:
    enabled: bool
    checks: list[StorageCheck]
    schema_version: int | None
    stats: StorageStats


@dataclass(frozen=True)
class StorageObjectInfo:
    object_id: str
    kind: str
    role: str | None
    storage_key: str
    sha256: str
    size_bytes: int
    mime_type: str | None
    file_exists: bool


@dataclass(frozen=True)
class StorageJobInfo:
    job_id: str
    job_type: str
    status: str
    updated_at: str
    error_message: str | None = None


@dataclass(frozen=True)
class StoragePaperInfo:
    found: bool
    query: str
    paper_id: str | None = None
    title: str | None = None
    year: int | None = None
    venue: str | None = None
    identifiers: list[tuple[str, str]] = field(default_factory=list)
    current_version_id: str | None = None
    objects: list[StorageObjectInfo] = field(default_factory=list)
    verified_pdf_status: str | None = None
    chunk_count: int | None = None
    index_status: list[dict[str, Any]] = field(default_factory=list)
    recent_jobs: list[StorageJobInfo] = field(default_factory=list)
    matches: list[tuple[str, str]] = field(default_factory=list)


class StorageDiagnostics:
    def __init__(self, storage: PaperOSStorageContext):
        self.storage = storage
        self.repo = storage.repository
        self.conn = storage.repository.conn

    def status(self, *, enabled: bool) -> StorageStatus:
        checks = [
            StorageCheck("enabled", enabled, "storage config enabled" if enabled else "storage config disabled"),
            StorageCheck("connection", self._connection_ok(), "SQLite connection responds to SELECT 1"),
            StorageCheck("sqlite_file", self.storage.paths.database_path.exists(), str(self.storage.paths.database_path)),
            StorageCheck("schema", self._schema_current(), "required PaperOS tables/columns are present"),
            StorageCheck("objects_dir", self.storage.paths.object_dir.is_dir(), str(self.storage.paths.object_dir)),
            StorageCheck("index_dir", self.storage.paths.index_dir.is_dir(), str(self.storage.paths.index_dir)),
            StorageCheck("plugin_data", self._under_plugin_data(), str(self.storage.paths.root_dir)),
        ]
        return StorageStatus(
            enabled=enabled,
            checks=checks,
            schema_version=self._schema_version(),
            stats=self.stats(),
        )

    def stats(self) -> StorageStats:
        return StorageStats(
            papers=self._count_table("papers"),
            objects=self._count_table("objects"),
            pdf_objects=self._count_table("objects", "kind = 'pdf'"),
            fulltext_locations=self._count_table("fulltext_locations"),
            chunks=self._count_table("paper_chunks"),
            jobs_by_status=self._jobs_by_status(),
            objects_size_bytes=self._sum_table("objects", "size_bytes", "deleted_at IS NULL"),
            sqlite_size_bytes=self._file_size(self.storage.paths.database_path),
            indexes_size_bytes=self._dir_size(self.storage.paths.index_dir),
        )

    def paper_info(self, query: str) -> StoragePaperInfo:
        query = query.strip()
        if not query:
            return StoragePaperInfo(found=False, query=query)

        row = self._find_paper(query)
        if row is None:
            matches = self._title_matches(query)
            return StoragePaperInfo(found=False, query=query, matches=matches)

        paper_id = str(row["id"])
        return StoragePaperInfo(
            found=True,
            query=query,
            paper_id=paper_id,
            title=str(row["canonical_title"]),
            year=row["year"],
            venue=row["venue"],
            identifiers=self._identifiers(paper_id),
            current_version_id=row["current_version_id"],
            objects=self._objects(paper_id),
            verified_pdf_status=self._verified_pdf_status(paper_id),
            chunk_count=self._count_table("paper_chunks", "paper_id = ?", (paper_id,)),
            index_status=self._index_status(paper_id),
            recent_jobs=self._recent_jobs(paper_id),
        )

    def _connection_ok(self) -> bool:
        try:
            self.conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def _schema_current(self) -> bool:
        try:
            return self.repo._schema_is_current()
        except Exception:
            return False

    def _schema_version(self) -> int | None:
        if not self._table_exists("schema_migrations"):
            return None
        row = self.conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        return int(row["version"]) if row and row["version"] is not None else None

    def _under_plugin_data(self) -> bool:
        try:
            plugin_data = (Path(get_astrbot_data_path()) / "plugin_data").resolve()
            root = self.storage.paths.root_dir.resolve()
            return root == plugin_data or plugin_data in root.parents
        except Exception:
            return False

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _count_table(
        self,
        table_name: str,
        where: str | None = None,
        params: tuple[Any, ...] = (),
    ) -> int | None:
        if not self._table_exists(table_name):
            return None
        sql = f"SELECT COUNT(*) AS count FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        row = self.conn.execute(sql, params).fetchone()
        return int(row["count"]) if row else 0

    def _sum_table(self, table_name: str, column: str, where: str | None = None) -> int | None:
        if not self._table_exists(table_name):
            return None
        sql = f"SELECT COALESCE(SUM({column}), 0) AS total FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        row = self.conn.execute(sql).fetchone()
        return int(row["total"]) if row else 0

    def _jobs_by_status(self) -> dict[str, int]:
        if not self._table_exists("paper_jobs"):
            return {}
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM paper_jobs GROUP BY status"
        ).fetchall()
        out = {status: 0 for status in ("pending", "running", "done", "failed")}
        for row in rows:
            out[str(row["status"])] = int(row["count"])
        return out

    def _find_paper(self, query: str) -> sqlite3.Row | None:
        row = self.conn.execute("SELECT * FROM papers WHERE id = ? LIMIT 1", (query,)).fetchone()
        if row:
            return row

        for scheme in ("doi", "arxiv"):
            value = normalize_identifier(scheme, query.removeprefix(f"{scheme}:").strip())
            if not value:
                continue
            row = self.conn.execute(
                """
                SELECT p.* FROM papers p
                JOIN paper_identifiers i ON i.paper_id = p.id
                WHERE i.scheme = ? AND i.value = ?
                LIMIT 1
                """,
                (scheme, value),
            ).fetchone()
            if row:
                return row

        title_norm = normalize_text(query)
        if not title_norm:
            return None
        row = self.conn.execute(
            "SELECT * FROM papers WHERE title_norm = ? ORDER BY updated_at DESC LIMIT 1",
            (title_norm,),
        ).fetchone()
        if row:
            return row
        return self.conn.execute(
            "SELECT * FROM papers WHERE title_norm LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%{title_norm}%",),
        ).fetchone()

    def _title_matches(self, query: str, *, limit: int = 5) -> list[tuple[str, str]]:
        title_norm = normalize_text(query)
        if not title_norm:
            return []
        rows = self.conn.execute(
            """
            SELECT id, canonical_title FROM papers
            WHERE title_norm LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (f"%{title_norm}%", limit),
        ).fetchall()
        return [(str(row["id"]), str(row["canonical_title"])) for row in rows]

    def _identifiers(self, paper_id: str) -> list[tuple[str, str]]:
        rows = self.conn.execute(
            """
            SELECT scheme, value FROM paper_identifiers
            WHERE paper_id = ?
            ORDER BY scheme, value
            """,
            (paper_id,),
        ).fetchall()
        return [(str(row["scheme"]), str(row["value"])) for row in rows]

    def _objects(self, paper_id: str) -> list[StorageObjectInfo]:
        rows = self.conn.execute(
            """
            SELECT o.*, l.role FROM objects o
            JOIN paper_object_links l ON l.object_id = o.id
            WHERE l.paper_id = ?
            ORDER BY o.created_at DESC
            """,
            (paper_id,),
        ).fetchall()
        out: list[StorageObjectInfo] = []
        for row in rows:
            storage_key = str(row["storage_key"])
            out.append(
                StorageObjectInfo(
                    object_id=str(row["id"]),
                    kind=str(row["kind"]),
                    role=row["role"],
                    storage_key=storage_key,
                    sha256=str(row["sha256"]),
                    size_bytes=int(row["size_bytes"]),
                    mime_type=row["mime_type"],
                    file_exists=self.storage.object_store.exists(storage_key),
                )
            )
        return out

    def _verified_pdf_status(self, paper_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT status, object_id, page_count, size_bytes FROM fulltext_locations
            WHERE paper_id = ? AND status = 'verified_pdf'
            ORDER BY last_seen_at DESC
            LIMIT 1
            """,
            (paper_id,),
        ).fetchone()
        if not row:
            return None
        linked = "linked" if row["object_id"] else "not linked"
        pages = f", pages={row['page_count']}" if row["page_count"] is not None else ""
        size = f", bytes={row['size_bytes']}" if row["size_bytes"] is not None else ""
        return f"{row['status']} ({linked}{pages}{size})"

    def _index_status(self, paper_id: str) -> list[dict[str, Any]]:
        if not self._table_exists("index_status"):
            return []
        rows = self.conn.execute(
            """
            SELECT index_name, status, profile, updated_at, message
            FROM index_status
            WHERE paper_id = ?
            ORDER BY updated_at DESC
            """,
            (paper_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _recent_jobs(self, paper_id: str, *, limit: int = 5) -> list[StorageJobInfo]:
        if not self._table_exists("paper_jobs"):
            return []
        rows = self.conn.execute(
            """
            SELECT id, job_type, status, updated_at, error_message
            FROM paper_jobs
            WHERE paper_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (paper_id, limit),
        ).fetchall()
        return [
            StorageJobInfo(
                job_id=str(row["id"]),
                job_type=str(row["job_type"]),
                status=str(row["status"]),
                updated_at=str(row["updated_at"]),
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def _file_size(self, path: Path) -> int | None:
        return path.stat().st_size if path.exists() else None

    def _dir_size(self, path: Path) -> int | None:
        if not path.exists():
            return None
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total
