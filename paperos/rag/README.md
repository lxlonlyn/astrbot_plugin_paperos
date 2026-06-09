# rag

Local retrieval, evidence-pack construction, embedding/vector indexing, and evidence-based generation.

Current retrieval implementation starts with storage-owned FTS and can use
storage-owned vector search when AstrBot embedding context is available.

RAG starts from storage-owned document data:

```text
storage chunks / FTS / normalized document
  -> RAG retrieval
  -> EvidencePack
  -> answer / analysis
```

RAG must not parse PDFs, call GROBID, download PDFs, or call `PaperSearchService` directly.

Implemented entry points:

- `RagService.retrieve_local(query, filters=None)`
- `RagService.build_evidence_pack(query, chunks)`
- `RagService.retrieve_evidence(query, filters=None)`
- `RagIndexService.index_parser_run(parser_run_id)`
- `RagIndexService.index_paper(paper_id)`
- `RagIndexService.index_pending_job(job)`
- `/paperos rag <query>` evidence chunk output

FTS retrieval reads `paper_chunks_fts`, `paper_chunks`, neighbor chunks, and paper citation metadata through the storage repository. Vector retrieval embeds the query with an AstrBot-configured embedding provider, calls storage `vector_index.search(...)`, then resolves returned `chunk_id` values back through the storage repository. If vector retrieval is unavailable or fails, `RagService` falls back to FTS-only evidence retrieval. It does not call searcher or LLM.

Phase 2 indexing resolves AstrBot-configured embedding providers through `context.get_all_embedding_providers()`. PaperOS does not implement Qwen/OpenAI/etc. embedding providers itself; it calls the resolved provider's `get_dim()` and prefers AstrBot `get_embeddings_batch(texts, batch_size=...)`, falling back to batched `get_embeddings(list[str])` only when needed.

RAG indexing receives storage-owned `LocalVectorIndex` and writes storage `VectorRecord` objects. Vector records are rebuildable and must not include chunk text; real text and metadata stay in storage.

If local evidence suggests external literature expansion is needed, RAG should return search expansion hints to a command/workflow layer. The workflow may then build a search context and explicitly call searcher.
