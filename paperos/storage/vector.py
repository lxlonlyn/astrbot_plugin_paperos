from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .interfaces import LocalVectorIndex, VectorRecord, VectorSearchRecord


class VectorIndexError(RuntimeError):
    pass


class LanceDBVectorIndex(LocalVectorIndex):
    """LanceDB-backed storage-owned vector index.

    The vector index stores rebuildable embedding records only. SQLite remains
    the source of truth for chunk text, paper metadata, sections, and pages.
    """

    def __init__(self, path: Path, *, table_name: str = "chunk_embeddings"):
        self.path = Path(path)
        self.table_name = table_name

    async def upsert_vectors(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        rows = [self._record_to_row(record) for record in records]
        db = self._connect()
        if self.table_name not in set(db.table_names()):
            db.create_table(self.table_name, data=rows)
            return

        table = db.open_table(self.table_name)
        for row in rows:
            table.delete("id = " + _quote_lancedb_value(str(row["id"])))
        table.add(rows)

    async def search(
        self,
        vector: list[float],
        *,
        limit: int = 20,
        profile: str | None = None,
    ) -> list[VectorSearchRecord]:
        db = self._connect()
        if self.table_name not in set(db.table_names()):
            return []

        query = db.open_table(self.table_name).search(vector)
        if profile:
            query = query.where("profile = " + _quote_lancedb_value(profile))
        rows = query.limit(max(1, int(limit))).to_list()
        return [
            VectorSearchRecord(
                chunk_id=str(row["chunk_id"]),
                score=_row_to_score(row),
            )
            for row in rows
            if row.get("chunk_id")
        ]

    def _record_to_row(self, record: VectorRecord) -> dict[str, Any]:
        row = asdict(record)
        row["profile"] = row["profile"] or _default_profile(record)
        return row

    def _connect(self):
        try:
            import lancedb  # type: ignore
        except Exception as exc:
            raise VectorIndexError(
                "LanceDB is not installed. Install lancedb before running vector indexing "
                "or configure storage.vector_backend to a supported installed backend."
            ) from exc

        self.path.mkdir(parents=True, exist_ok=True)
        return lancedb.connect(str(self.path))


def _default_profile(record: VectorRecord) -> str:
    return f"{record.provider_id}:{record.embedding_model}"


def _quote_lancedb_value(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _row_to_score(row: dict[str, Any]) -> float:
    for key in ("_score", "score"):
        if key in row:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return 0.0
    try:
        distance = float(row.get("_distance"))
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / (1.0 + max(0.0, distance))
