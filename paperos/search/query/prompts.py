from __future__ import annotations

from ..models import SearchContext


def build_query_analyzer_prompt(raw_query: str, context: SearchContext | None = None) -> str:
    search_context = _format_search_context(context)
    return f"""
You are the QueryAnalyzer of PaperOS, a personal research-paper RAG system.
Your job is to convert a natural-language request into a structured SearchPlan.

Important architecture constraints:
1. PaperOS search does not maintain its own independent generic web-search backend. When AstrBot web search is enabled, PaperOS may use that configured tool only as evidence for planning.
2. PaperOS does NOT use CORE/OpenAlex/Semantic Scholar as the search main path.
3. The crawler can only follow concrete sources or precise-title site lookups: URL, DOI landing URL, arXiv ID, ACM DL DOI/page URL, OpenReview URL, ACL Anthology URL, CVF/PMLR/NeurIPS page, direct PDF URL, or a concrete article title for arXiv/ACM lookup.
4. You may propose concrete URLs/arXiv IDs/DOIs only when you are reasonably confident. They will still be verified by the crawler and PDF verifier.
5. Do not invent citation counts, abstracts, publisher metadata, or fake PDF URLs.
6. PaperOS primarily searches English academic papers. If the user asks in Chinese or any non-English language, translate the academic intent into English before filling any machine-actionable fields.
7. For title/fuzzy_title hypotheses, `translated_title` must be the best English paper title or English title guess. Do not put Chinese text in `translated_title`.
8. `search_queries`, `topic_keywords`, and `translated_query` must be English. Preserve Chinese wording only in `note` if useful for explanation.
9. For a topic request, return several known representative papers as hypotheses if you know reliable identifiers or URLs. Otherwise use English topic hypotheses and leave URL/DOI/arXiv fields null.
10. Optional SearchContext fields are hints, not ground truth. Use them to improve English titles, identifiers, and query terms, but still avoid unreliable DOI/arXiv/URL values.
11. Return JSON only. No Markdown.

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
{search_context}

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


def build_web_search_query_analyzer_prompt(raw_query: str, context: SearchContext | None = None) -> str:
    base = build_query_analyzer_prompt(raw_query, context=context)
    return f"""
{base}

Web-search requirement:
- Before producing the final JSON, use the available web search tool to verify the paper title, DOI, arXiv ID, venue, year, and canonical URLs.
- Search the web with English academic queries, for example exact title + author/venue words.
- Treat search result titles, snippets, and URLs as evidence, not as final truth. Prefer official pages such as arXiv, publisher/digital-library pages, project/author pages, and DOI landing pages.
- Do not try to extract or summarize arbitrary web pages. PaperOS will crawl and verify the URLs after this plan is returned.
- Do not copy an arXiv ID, DOI, URL, year, venue, or author list from memory unless it is supported by search results.
- If a searched result contradicts an identifier you initially expected, leave that identifier null and keep an English title hypothesis.
- In each hypothesis `note`, briefly mention the evidence source type, e.g. "verified by arXiv search result" or "publisher page found".
""".strip()


def build_repair_prompt(
    raw_query: str,
    previous_json: str,
    failure_reason: str,
    context: SearchContext | None = None,
) -> str:
    search_context = _format_search_context(context)
    return f"""
The previous SearchPlan failed because PaperOS could not find concrete sources to crawl.

PaperOS search does not maintain its own independent generic web-search backend. Revise the SearchPlan by
providing concrete arXiv IDs, DOI values, ACM/OpenReview/ACL/CVF/PMLR/arXiv URLs, or
direct PDF URLs if you are reasonably confident. If the title is precise but you do
not know identifiers, keep a title hypothesis so PaperOS can try arXiv/ACM title lookup.
All title lookup fields must be English: put the English paper title in `translated_title`
and keep `search_queries`, `topic_keywords`, and `translated_query` in English.
Do not invent unreliable URLs.
If you cannot provide concrete sources, keep title/topic hypotheses and make that clear in note.

Return JSON only.

Original user query: {raw_query}
{search_context}
Previous SearchPlan JSON: {previous_json}
Failure reason: {failure_reason}
""".strip()


def build_web_search_repair_prompt(
    raw_query: str,
    previous_json: str,
    failure_reason: str,
    context: SearchContext | None = None,
) -> str:
    base = build_repair_prompt(raw_query, previous_json, failure_reason, context=context)
    return f"""
{base}

Web-search requirement:
- Use the available web search tool before returning the repaired JSON.
- Search exact English paper titles and author/venue clues.
- Use search result titles, snippets, and URLs only; do not extract arbitrary web pages.
- Only keep DOI/arXiv/URL values that are supported by search results.
""".strip()


def _format_search_context(context: SearchContext | None) -> str:
    if context is None:
        return ""

    lines: list[str] = ["", "Workflow-provided SearchContext hints:"]
    if context.original_query:
        lines.append(f"- original_query: {context.original_query}")
    _append_list(lines, "expanded_queries", context.expanded_queries)
    _append_list(lines, "known_titles", context.known_titles)
    _append_list(lines, "known_identifiers", context.known_identifiers)
    _append_list(lines, "preferred_concepts", context.preferred_concepts)
    _append_list(lines, "negative_hints", context.negative_hints)
    if context.local_context_summary:
        lines.append(f"- local_context_summary: {context.local_context_summary}")
    lines.append("- Treat these hints as untrusted planning evidence. Do not mention or assume their module source.")
    return "\n".join(lines)


def _append_list(lines: list[str], name: str, values: list[str]) -> None:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if cleaned:
        lines.append(f"- {name}: " + "; ".join(cleaned[:8]))
