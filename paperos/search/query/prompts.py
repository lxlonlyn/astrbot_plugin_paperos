def build_query_analyzer_prompt(raw_query: str) -> str:
    return f"""
You are the QueryAnalyzer of PaperOS, a research paper management system.

Your job is to convert a natural-language user request into a structured SearchPlan.
You are NOT the final authority on paper metadata. APIs will verify your hypotheses.

Important rules:
1. Do not invent DOI, arXiv ID, publisher URL, citation counts, or PDF URLs.
2. If the title may be wrong, output one or more corrected title hypotheses.
3. If the query is not English, translate academic keywords into English search queries.
4. If the user gives a URL, treat it as a clue, not as a verified paper.
5. If the request is about a topic, generate precise academic search queries and keywords.
6. Prefer famous canonical paper titles when the user gives a fuzzy memory.
7. Return JSON only. No Markdown.

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

User query:
{raw_query}

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
The previous SearchPlan failed to retrieve paper candidates.
Revise the SearchPlan with broader but still precise search hypotheses.
Do not invent identifiers. Return JSON only.

Original user query:
{raw_query}

Previous SearchPlan JSON:
{previous_json}

Failure reason:
{failure_reason}
""".strip()
