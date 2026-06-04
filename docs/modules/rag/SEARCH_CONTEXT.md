# RAG Search Context

RAG can help external search without calling searcher directly.

## Interface

```python
draft = await rag_service.build_search_context(query)
```

Returns `SearchContextDraft`.

## Fields

- `related_papers`
- `related_concepts`
- `aliases`
- `known_identifiers`
- `positive_query_terms`
- `negative_query_terms`
- `suggested_search_queries`
- `local_context_summary`

## Rule

RAG returns hints only. A command/workflow layer may convert those hints into searcher's SearchContext and explicitly call search.

Forbidden:

- `rag -> PaperSearchService`
- hidden web search inside RAG
- LLM-generated search terms without local evidence attribution

## Intended Use

```text
user query
  -> RAG build_search_context
  -> workflow builds SearchContext
  -> workflow calls search explicitly
```

This keeps local evidence retrieval separate from online acquisition.
