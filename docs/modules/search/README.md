# Search module

`paperos.search` is responsible for online paper acquisition. It does not persist papers and does not build embeddings.

## Corrected pipeline

```text
User query
  -> AstrBotLLMQueryAnalyzer
  -> SearchPlan
  -> TargetedPaperCrawler
  -> DomainResolver
  -> FulltextVerifier
  -> PaperSearchResult
```

## LLM usage

`AstrBotLLMQueryAnalyzer` uses AstrBot's LLM interface. It resolves the current chat provider from the event when no provider is configured, then calls `context.llm_generate(...)`.

The LLM does not decide that a paper is valid. It only proposes hypotheses and concrete sources. Every PDF is still downloaded and verified by `FulltextVerifier`.

## No generic web search backend

There is no `web_search.endpoint` in the corrected design. There is no DuckDuckGo HTML adapter. Searcher does not call CORE/OpenAlex/Semantic Scholar as the main path.

The crawler only follows concrete sources or precise-title site lookups:

- arXiv ID or arXiv URL;
- DOI landing URL;
- direct PDF URL;
- OpenReview URL;
- ACL Anthology URL;
- ACM DL DOI/page URL;
- precise title lookup on arXiv and ACM DL, with a small result limit;
- publisher/project/author pages explicitly proposed by the LLM or user.

For vague title/topic requests, a capable LLM may propose known arXiv IDs, DOI values, or canonical URLs. If it cannot, PaperOS should return a clear `not_found` message asking for more concrete clues.

The precise-title lookup is not a generic search backend. It is intended for cases where QueryAnalyzer has already reduced the user request to one or more concrete article names, such as a SIGGRAPH paper title. Returned candidates still go through scoring, dedup, disambiguation, and local PDF verification.

## Files

- `service.py`: AstrBot-facing facade.
- `pipeline.py`: orchestration.
- `query/analyzer.py`: AstrBot LLM call.
- `query/prompts.py`: SearchPlan prompt.
- `crawl/targeted.py`: follows concrete sources only.
- `crawl/domain_resolver.py`: maps known domains such as arXiv, ACM DL, OpenReview, and ACL Anthology to candidate PDF URLs.
- `acquire/verifier.py`: downloads and strictly validates PDFs.
- `resolve/*`: scoring, dedup, disambiguation.

## Deprecated/legacy files

The following old modules should not be part of the corrected main path:

- `search/providers/`
- `search/core_client.py`
- `search/core_query.py`
- `search/query_router.py`
- `search/ranker.py`
- `search/crawl/search_engine.py`

`search/crawl/search_engine.py` may remain as a compatibility stub during migration, but no new code should import it.
