# rag

Future module for chunk retrieval, citation-aware answer generation, and local index integration.

RAG must not call `PaperSearchService` directly.

If local evidence suggests external literature expansion is needed, RAG should return expansion
hints to a command/workflow layer. The workflow may then build `paperos.search.models.SearchContext`
and explicitly call searcher.
