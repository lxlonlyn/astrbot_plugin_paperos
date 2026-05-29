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

If AstrBot's current session config enables `provider_settings.web_search`, QueryAnalyzer still first calls plain `context.llm_generate(...)` to build a structured English `SearchPlan`. PaperOS then directly calls exactly one AstrBot built-in web-search tool for the configured provider, such as Tavily, BoCha, Brave, Firecrawl, or Baidu AI Search. This stage is code-controlled, not a model tool loop: `query_analyzer.max_web_search_queries` is capped at 5, page-extraction tools are not used, and returned URLs/snippets are added as evidence for the targeted crawler.

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

Chinese user queries are allowed, but machine-actionable search fields should be English. `translated_title`, `translated_query`, `topic_keywords`, and `search_queries` are expected to contain English academic terms. If the fallback analyzer only sees Chinese text and no DOI/arXiv/URL, it will not use the Chinese text for arXiv/ACM title lookup.

LLM-proposed identifiers are not trusted as facts. When a hypothesis contains a title plus a concrete DOI/arXiv ID/URL, the fetched landing-page metadata must still match the planned title. If the title disagrees, PaperOS rejects that identifier candidate and keeps trying precise-title lookup.

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
