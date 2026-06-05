from __future__ import annotations

import asyncio
import sys
import types

from paperos.storage.interfaces import VectorRecord
from paperos.storage.vector import LanceDBVectorIndex


class FakeLanceQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filter_expr = None
        self.limit_value = None

    def where(self, expr: str):
        self.filter_expr = expr
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def to_list(self):
        rows = self.rows
        if self.filter_expr:
            profile = self.filter_expr.split("=", 1)[1].strip().strip("'")
            rows = [row for row in rows if row.get("profile") == profile]
        return rows[: self.limit_value]


class FakeLanceTable:
    def __init__(self, rows):
        self.rows = rows
        self.deleted: list[str] = []

    def delete(self, expr: str):
        self.deleted.append(expr)
        record_id = expr.split("=", 1)[1].strip().strip("'")
        self.rows[:] = [row for row in self.rows if row.get("id") != record_id]

    def add(self, records):
        self.rows.extend(records)

    def search(self, vector):
        return FakeLanceQuery(self.rows)


class FakeLanceDB:
    def __init__(self):
        self.tables = {}

    def table_names(self):
        return list(self.tables)

    def create_table(self, name, data):
        self.tables[name] = FakeLanceTable(list(data))

    def open_table(self, name):
        return self.tables[name]


def test_lancedb_vector_index_upserts_without_chunk_text(monkeypatch, tmp_path):
    async def run():
        fake_db = FakeLanceDB()
        fake_module = types.SimpleNamespace(connect=lambda path: fake_db)
        monkeypatch.setitem(sys.modules, "lancedb", fake_module)

        index = LanceDBVectorIndex(tmp_path / "lancedb", table_name="chunk_embeddings")
        await index.upsert_vectors(
            [
                VectorRecord(
                    id="vec-a",
                    chunk_id="chunk-a",
                    paper_id="paper-a",
                    vector=[1.0, 0.0, 0.0],
                    embedding_model="model-a",
                    provider_id="provider-a",
                    content_hash="hash-a",
                    chunk_index=0,
                    section_path="Intro",
                    profile="provider-a:model-a",
                ),
                VectorRecord(
                    id="vec-b",
                    chunk_id="chunk-b",
                    paper_id="paper-a",
                    vector=[0.0, 1.0, 0.0],
                    embedding_model="model-b",
                    provider_id="provider-a",
                    content_hash="hash-b",
                    profile="provider-a:model-b",
                ),
            ]
        )
        rows = fake_db.tables["chunk_embeddings"].rows
        rows[0]["_distance"] = 0.25
        rows[1]["_distance"] = 1.0

        assert "text" not in rows[0]
        results = await index.search([1.0, 0.0, 0.0], profile="provider-a:model-a")

        assert [item.chunk_id for item in results] == ["chunk-a"]
        assert results[0].score == 0.8

    asyncio.run(run())
