# Storage Document Processing

Storage owns local document processing for already archived PDFs.

## Flow

```text
storage PDF object
  -> parser_runs row
  -> local GROBID REST API or fallback parser
  -> raw TEI XML object
  -> PaperOS normalized document JSON object
  -> document_sections / document_blocks / extracted_assets / paper_references
  -> paper_chunks
  -> paper_chunks_fts
  -> enqueue rag_embed_chunks
```

## GROBID

GROBID `processFulltextDocument` returns TEI XML for a full scientific document. TEI can represent nested sections, paragraphs, formulas, figures, tables, bibliography and reference links. PaperOS stores the raw TEI as an object for reproducibility, but RAG should consume PaperOS normalized JSON and SQL rows instead of raw TEI.

The GROBID REST endpoint is configured by `storage.grobid_base_url`; the default is `http://localhost:8070`. `storage.grobid_timeout_seconds` controls the request timeout. If the service cannot be reached, storage document processing should fail with a clear message asking the user to check the configured URL and whether GROBID is running.

## Normalized Document

The normalized document is PaperOS-owned JSON derived from parser output. It should preserve enough structure for chunking and retrieval while hiding parser-specific TEI details from RAG.

Expected major parts:

- document metadata;
- section tree;
- linear blocks;
- extracted assets;
- bibliography references;
- parser metadata.

## SQL Rows

- `parser_runs`: one row per parse attempt.
- `document_sections`: section tree.
- `document_blocks`: linear text and structural blocks.
- `extracted_assets`: figures, tables, formulas and related text/object links.
- `paper_references`: bibliography entries.
- `paper_chunks`: retrievable chunks with `embedding_text`.
- `paper_chunks_fts`: SQLite FTS5 table maintained by storage.

## Jobs

- `storage_parse_pdf`: storage worker parses a PDF object into document rows, chunks and FTS.
- `rag_embed_chunks`: RAG worker or `/paperos search` post-processing embeds chunks and updates vector/index status.

Storage enqueues `storage_parse_pdf` after importing a verified PDF and immediately attempts one synchronous document-processing pass in the `/paperos search` workflow. On success, it marks `storage_parse_pdf` done and enqueues `rag_embed_chunks`. The workflow may then call RAG indexing for the returned `parser_run_id` and mark that `rag_embed_chunks` job done/failed. On GROBID or parser failure, it keeps the imported paper/PDF, marks `storage_parse_pdf` failed, and returns a clear import summary message.

## Non-Goals

Storage must not:

- search the internet;
- download PDF URLs;
- call LLM providers;
- call embedding providers;
- decide embedding models, retrieval policy, or answer generation;
- generate answers.
