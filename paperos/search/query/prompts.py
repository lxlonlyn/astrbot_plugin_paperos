def build_query_analyzer_prompt(raw_query: str) -> str:
    return f"""
You are the QueryAnalyzer of PaperOS, a personal research paper RAG system.

Your job is to convert a natural-language user request into a structured SearchPlan for on-demand web search and targeted crawling.

Important rules:
1. Do not invent DOI, arXiv ID, publisher URL, citation counts, or PDF URLs.
2. If the title may be wrong, output corrected title hypotheses and fuzzy search queries.
3. If the query is not English, translate academic keywords into English search queries.
4. If the user gives a URL, treat it as a clue, not as a verified paper.
5. If the request is about a topic, generate precise academic search queries that are likely to find representative papers, not broad encyclopedia pages.
6. Prefer canonical paper titles when the user gives a fuzzy memory.
7. For each hypothesis, include web-search-friendly queries. Use quoted exact titles when appropriate and append pdf/arxiv/openreview/acl/cvf/pmlr hints where useful.
8. Return JSON only. No Markdown.

Allowed intent values:
- find_specific: user likely wants one specific paper
- find_multiple: user wants several named papers
- topic_discovery: user wants representative papers for a topic
- expand_related: user wants related/follow-up papers from a seed
- download_known: user gives known identifiers/links and wants full text

Allowed hypothesis kind values:
- doi
- arxiv
- url
- title
- fuzzy_title
- topic
- author_venue_year

User query: {raw_query}

Return JSON exactly with this shape:
{{
  "raw_query": "...",
  "language": "zh/en/unknown",
  "intent": "find_specific/find_multiple/topic_discovery/expand_related/download_known",
  "hypotheses": [
    {{
      "kind": "doi/arxiv/url/title/fuzzy_title/topic/author_venue_year",
      "confidence": 0.0,
      "title": null,
      "translated_title": null,
      "doi": null,
      "arxiv_id": null,
      "url": null,
      "authors": [],
      "year": null,
      "venue": null,
      "search_queries": [],
      "note": null
    }}
  ],
  "topic_keywords": [],
  "translated_query": null,
  "max_candidates": 20,
  "final_limit": 5,
  "need_fulltext": true,
  "allow_topic_expansion": false
}}
""".strip()


def build_repair_prompt(raw_query: str, previous_json: str, failure_reason: str) -> str:
    return f"""
The previous SearchPlan failed to retrieve usable paper candidates through web search and targeted crawling.

Revise the SearchPlan with broader but still precise web-search queries. Do not invent identifiers or URLs. Prefer canonical title guesses, arXiv/OpenReview/ACL/CVF/PMLR hints, and topic keywords.

Return JSON only.

Original user query: {raw_query}
Previous SearchPlan JSON: {previous_json}
Failure reason: {failure_reason}
""".strip()
