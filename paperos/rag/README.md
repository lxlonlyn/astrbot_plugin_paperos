# rag

Local retrieval, evidence-pack construction, embedding/vector indexing, and evidence-based generation.

Current implementation is Phase 1: FTS-only retrieval over storage-owned chunks.

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

Phase 1 reads `paper_chunks_fts`, `paper_chunks`, neighbor chunks, and paper citation metadata through the storage repository. It does not call an embedding provider, vector index, searcher, or LLM.

Phase 2 indexing resolves AstrBot-configured embedding providers through `context.get_all_embedding_providers()`. PaperOS does not implement Qwen/OpenAI/etc. embedding providers itself; it calls the resolved provider's `get_dim()` and prefers AstrBot `get_embeddings_batch(texts, batch_size=...)`, falling back to batched `get_embeddings(list[str])` only when needed.

If local evidence suggests external literature expansion is needed, RAG should return search expansion hints to a command/workflow layer. The workflow may then build a search context and explicitly call searcher.
