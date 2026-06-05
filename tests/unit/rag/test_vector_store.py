from __future__ import annotations

import asyncio
import sys
import types

from paperos.rag.vector import LanceDBVectorStore


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
            rows = [row for row in rows if row.get("embedding_model") == profile]
        return rows[: self.limit_value]


class FakeLanceTable:
    def __init__(self, rows):
        self.rows = rows
        self.deleted: list[str] = []

    def delete(self, expr: str):
        self.deleted.append(expr)

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


def test_lancedb_vector_store_upserts_and_searches_chunk_ids(monkeypatch, tmp_path):
    async def run():
        fake_db = FakeLanceDB()
        fake_module = types.SimpleNamespace(connect=lambda path: fake_db)
        monkeypatch.setitem(sys.modules, "lancedb", fake_module)

        store = LanceDBVectorStore(tmp_path / "vector", table_name="chunk_embeddings")
        await store.upsert_vectors(
            [
                {
                    "chunk_id": "chunk-a",
                    "embedding_model": "emb-a:dim3",
                    "vector": [1.0, 0.0, 0.0],
                    "_distance": 0.25,
                },
                {
                    "chunk_id": "chunk-b",
                    "embedding_model": "emb-b:dim3",
                    "vector": [0.0, 1.0, 0.0],
                    "_distance": 1.0,
                },
            ]
        )
        fake_db.tables["chunk_embeddings"].rows[0]["_distance"] = 0.25
        fake_db.tables["chunk_embeddings"].rows[1]["_distance"] = 1.0

        results = await store.search([1.0, 0.0, 0.0], profile="emb-a:dim3")

        assert [item.chunk_id for item in results] == ["chunk-a"]
        assert results[0].score == 0.8

    asyncio.run(run())
