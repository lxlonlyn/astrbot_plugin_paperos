def build_query_analyzer_prompt(raw_query: str) -> str:
    return f"""
You are the QueryAnalyzer of PaperOS, a personal research-paper RAG system.
Your job is to convert a natural-language request into a structured SearchPlan.

Important architecture constraints:
1. PaperOS does NOT use a generic web-search backend in this stage.
2. PaperOS does NOT use CORE/OpenAlex/Semantic Scholar as the search main path.
3. The crawler can only follow concrete sources: URL, DOI landing URL, arXiv ID, OpenReview URL, ACL Anthology URL, CVF/PMLR/NeurIPS page, or direct PDF URL.
4. You may propose concrete URLs/arXiv IDs/DOIs only when you are reasonably confident. They will still be verified by the crawler and PDF verifier.
5. Do not invent citation counts, abstracts, publisher metadata, or fake PDF URLs.
6. If the query is vague or in Chinese, translate academic keywords and, when possible, output well-known canonical paper identifiers.
7. For a topic request, return several known representative papers as hypotheses if you know reliable identifiers or URLs. Otherwise use title/topic hypotheses and leave URL/DOI/arXiv fields null.
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
The previous SearchPlan failed because PaperOS could not find concrete sources to crawl.

PaperOS has no generic web-search backend in this stage. Revise the SearchPlan by
providing concrete arXiv IDs, DOI values, OpenReview/ACL/CVF/PMLR/arXiv URLs, or
direct PDF URLs if you are reasonably confident. Do not invent unreliable URLs.
If you cannot provide concrete sources, keep title/topic hypotheses and make that clear in note.

Return JSON only.

Original user query: {raw_query}
Previous SearchPlan JSON: {previous_json}
Failure reason: {failure_reason}
""".strip()
