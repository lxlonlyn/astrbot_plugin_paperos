from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class VectorIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    score: float


class VectorStore(Protocol):
    async def upsert_vectors(self, records: list[dict[str, Any]]) -> None: ...

    async def search(
        self,
        vector: list[float],
        *,
        limit: int = 20,
        profile: str | None = None,
    ) -> list[VectorSearchResult]: ...


class LanceDBVectorStore:
    """LanceDB-backed vector index.

    LanceDB stores rebuildable vector records only. Storage SQLite remains the
    source of truth for chunk text and paper metadata.
    """

    def __init__(self, path: Path, *, table_name: str = "chunk_embeddings"):
        self.path = Path(path)
        self.table_name = table_name

    async def upsert_vectors(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        db = self._connect()
        table_names = set(db.table_names())
        if self.table_name not in table_names:
            db.create_table(self.table_name, data=records)
            return

        table = db.open_table(self.table_name)
        for record in records:
            table.delete(
                "chunk_id = "
                + _quote_lancedb_value(str(record["chunk_id"]))
                + " AND embedding_model = "
                + _quote_lancedb_value(str(record["embedding_model"]))
            )
        table.add(records)

    async def search(
        self,
        vector: list[float],
        *,
        limit: int = 20,
        profile: str | None = None,
    ) -> list[VectorSearchResult]:
        db = self._connect()
        if self.table_name not in set(db.table_names()):
            return []

        query = db.open_table(self.table_name).search(vector)
        if profile:
            query = query.where("embedding_model = " + _quote_lancedb_value(profile))
        rows = query.limit(max(1, int(limit))).to_list()
        return [
            VectorSearchResult(
                chunk_id=str(row["chunk_id"]),
                score=_distance_to_score(row.get("_distance")),
            )
            for row in rows
            if row.get("chunk_id")
        ]

    def _connect(self):
        try:
            import lancedb  # type: ignore
        except Exception as exc:
            raise VectorIndexError(
                "LanceDB is not installed. Install the plugin requirements or add lancedb "
                "before running RAG vector indexing."
            ) from exc

        self.path.mkdir(parents=True, exist_ok=True)
        return lancedb.connect(str(self.path))


def _quote_lancedb_value(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _distance_to_score(distance: object) -> float:
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / (1.0 + max(0.0, value))
