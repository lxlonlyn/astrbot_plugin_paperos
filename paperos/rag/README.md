# rag

Future module for local retrieval, evidence-pack construction, embedding/vector indexing, and evidence-based generation.

RAG starts from storage-owned document data:

```text
storage chunks / FTS / normalized document
  -> RAG retrieval
  -> EvidencePack
  -> answer / analysis
```

RAG must not parse PDFs, call GROBID, download PDFs, or call `PaperSearchService` directly.

If local evidence suggests external literature expansion is needed, RAG should return search expansion hints to a command/workflow layer. The workflow may then build a search context and explicitly call searcher.
