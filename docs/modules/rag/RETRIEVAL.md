# RAG Retrieval

## Phase 1: FTS-Only Retrieval

```text
query
  -> storage.search_chunks_fts(query, paper_id=None, limit=20)
  -> storage.get_chunks_by_ids(...)
  -> optional storage.get_neighbor_chunks(...)
  -> EvidencePack
```

FTS-only retrieval should be the first stable milestone.

## EvidenceBuilder

EvidenceBuilder should fetch:

- chunk id;
- paper id and title;
- section title/path;
- page start/end;
- chunk text;
- citation metadata;
- neighbor chunks when requested.

It returns an EvidencePack that can be passed to generation without extra database reads.

## Vector Retrieval

Current implementation includes a storage-owned vector retriever:

```text
query
  -> resolve AstrBot embedding provider
  -> provider.get_embeddings([query])
  -> storage.vector_index.search(query_vector, profile=...)
  -> repository.get_chunks_by_ids(chunk_ids)
  -> RetrievedChunk[]
```

Vector search only returns `chunk_id` and score. Real text, title, section, page and citation metadata must still be loaded from SQLite/storage. RAG may embed the query and orchestrate retrieval, but it must not instantiate LanceDB or read vector-index files directly.

If embedding provider resolution, query embedding, or vector index search fails, the service falls back to FTS-only retrieval instead of failing `/paperos rag`.

## Hybrid Retrieval

```text
query
  -> query embedding
  -> FTS top_k
  -> vector top_k
  -> RRF fusion
  -> neighbor expansion
  -> optional rerank
  -> EvidencePack
```

Initial RRF:

```text
score = 1 / (60 + rank_fts) + 1 / (60 + rank_vector)
```

Later versions may add weights, learned rerankers, or per-paper caps.

`/paperos rag <query>` should use hybrid evidence retrieval when `vector_index` and AstrBot context are available. If vector retrieval is unavailable, FTS remains the reliable baseline.

## Generation

AnswerBuilder must answer only from EvidencePack. If evidence is insufficient, it should say so and optionally produce search expansion hints for the workflow.
