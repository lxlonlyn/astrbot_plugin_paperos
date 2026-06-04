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

## Phase 3: Hybrid Retrieval

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

## Generation

AnswerBuilder must answer only from EvidencePack. If evidence is insufficient, it should say so and optionally produce search expansion hints for the workflow.
