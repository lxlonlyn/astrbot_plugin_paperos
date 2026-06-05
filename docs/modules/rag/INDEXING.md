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

Current baseline implementation:

- `paperos.rag.providers.resolve_embedding_provider(context, provider_id="")`
- `paperos.rag.indexing.RagIndexService.index_parser_run(parser_run_id)`
- `paperos.rag.indexing.RagIndexService.index_paper(paper_id)`
- `paperos.rag.indexing.RagIndexService.index_pending_job(job)`

```text
rag_embed_chunks job
  -> workflow claims job
  -> RagIndexService reads storage chunks
  -> resolve AstrBot embedding provider
  -> provider.get_dim()
  -> provider.get_embeddings_batch(texts, batch_size=...)
     or fallback provider.get_embeddings(list[str]) per batch
  -> write LanceDB vector records
  -> update storage index_status
  -> workflow marks job done/failed
```

`RagIndexService` deliberately does not claim jobs or parse commands. It handles one explicit parser run, paper id, or decoded job payload.

Embedding providers are owned by AstrBot. PaperOS must not implement Qwen/OpenAI/etc. providers directly. It only resolves an already configured AstrBot embedding provider via `context.get_all_embedding_providers()`, then calls `get_dim()`. For chunk embeddings it first uses AstrBot's `get_embeddings_batch(texts, batch_size=...)` helper when available; if that method is absent, it falls back to calling `get_embeddings(list[str])` in PaperOS-sized batches.

## Recommended Vector Record

```text
id
chunk_id
paper_id
vector
embedding_model
provider_id
content_hash
section_path
page_start
page_end
chunk_type
parser_run_id
chunk_index
text
```

## Rules

- `embedding_model + content_hash` dedupes embedding work.
- Different embedding models must not share one logical index.
- Vector index is rebuildable.
- SQLite/storage chunks are the source of truth.
- RAG calls embedding providers; storage never does.
- Current implementation writes paper-level `index_status`; chunk-level embedding status can be added later if needed.

## Job Names

Recommended:

- storage document processing: `storage_parse_pdf`
- RAG embedding: `rag_embed_chunks`
- vector index build/rebuild: `build_vector_index`

Existing code may use transitional names; prefer the names above for new work.
