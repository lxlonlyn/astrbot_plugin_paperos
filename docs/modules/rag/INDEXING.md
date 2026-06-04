# RAG Indexing

Indexing is phased. Phase 1 intentionally avoids embeddings.

## Phase 1: FTS-Only

RAG uses storage-owned `paper_chunks_fts`.

```text
query
  -> repository.search_chunks_fts(...)
  -> RetrievedChunk[]
  -> EvidencePack
```

This validates storage document processing before adding embedding complexity.

## Phase 2: Embedding + Vector Index

```text
rag_embed_chunks job
  -> load unembedded chunks
  -> batch embedding provider
  -> write vector index
  -> update index_status
```

## Recommended Vector Record

```text
chunk_id
paper_id
vector
embedding_model
content_hash
section_path
page_start
chunk_type
```

## Rules

- `embedding_model + content_hash` dedupes embedding work.
- Different embedding models must not share one logical index.
- Vector index is rebuildable.
- SQLite/storage chunks are the source of truth.
- RAG calls embedding providers; storage never does.

## Job Names

Recommended:

- storage document processing: `storage_parse_pdf`
- RAG embedding: `rag_embed_chunks`
- vector index build/rebuild: `build_vector_index`

Existing code may use transitional names; prefer the names above for new work.
