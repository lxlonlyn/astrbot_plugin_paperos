# RAG Architecture

RAG consumes local evidence from storage. It does not own PDF parsing, GROBID, chunking, object archival, or search.

## Boundary

```text
storage document processing
  -> paper_chunks / paper_chunks_fts / normalized document
  -> RAG
```

RAG owns:

- retrieval over local chunks;
- embedding provider calls;
- vector index writes;
- hybrid retrieval;
- EvidencePack construction;
- evidence-grounded answer and analysis workflows;
- search expansion hints for workflow use.

RAG does not own:

- PDF -> TEI;
- TEI -> normalized document;
- chunk generation;
- FTS table construction;
- searcher invocation.

## Recommended Package Shape

```text
paperos/rag/
  models.py
  service.py
  config.py
  embeddings/
  indexes/
  retrieval/
  context/
  generation/
  jobs.py
```

Do not create all folders before they are needed. Use this as a growth map.

## Core DTOs

- `RetrievedChunk`: chunk id, paper id, title, section, page, score, source rank, text preview/full text.
- `EvidencePack`: ordered chunks with citation metadata and compact context text.
- `AnswerDraft`: answer text plus citations and residual uncertainty.
- `SearchContextDraft`: local hints for an external workflow to expand search.

## Service Shape

```python
class RagService:
    async def retrieve_local(self, query: str, filters=None) -> list[RetrievedChunk]: ...
    async def build_evidence_pack(self, query: str, chunks: list[RetrievedChunk]) -> EvidencePack: ...
    async def answer(self, query: str, filters=None) -> AnswerDraft: ...
    async def build_search_context(self, query: str) -> SearchContextDraft: ...
```

`RagService` may depend on storage repository interfaces and LLM/embedding adapters. It must not import `paperos.search.service`.
