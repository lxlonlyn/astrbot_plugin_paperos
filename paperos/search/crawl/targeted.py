from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from astrbot.api import logger

from ...config import CrawlerConfig, WebSearchConfig
from ..models import FulltextLocation, HypothesisKind, PaperCandidate, SearchIntent, SearchPlan, WebSearchResult
from .domain_resolver import DomainResolver
from .html import ExtractedHTML, parse_paper_html
from .search_engine import WebSearchEngine
from .url_tools import (
    canonical_url,
    extract_arxiv_id,
    extract_doi,
    host_of,
    looks_like_http_url,
    looks_like_pdf_url,
    strip_html,
)


class TargetedPaperCrawler:
    """On-demand crawler for a small number of paper candidates.

    The crawler is intentionally query-driven. It does not enumerate full
    conference/year pages; it only inspects pages returned from the SearchPlan's
    focused web queries.
    """

    def __init__(
        self,
        *,
        crawler_cfg: CrawlerConfig,
        web_cfg: WebSearchConfig,
        search_engine: WebSearchEngine,
        domain_resolver: DomainResolver | None = None,
    ):
        self.crawler_cfg = crawler_cfg
        self.web_cfg = web_cfg
        self.search_engine = search_engine
        self.domain_resolver = domain_resolver or DomainResolver()
        self._client = httpx.AsyncClient(
            timeout=crawler_cfg.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": web_cfg.user_agent, "Accept": "text/html,application/pdf,*/*;q=0.5"},
        )

    async def discover(self, plan: SearchPlan) -> list[PaperCandidate]:
        if not self.crawler_cfg.enabled:
            logger.debug("[PaperOS][TargetedCrawler] disabled")
            return []

        direct = self._direct_candidates(plan)
        queries = self._build_queries(plan)
        logger.debug(
            "[PaperOS][TargetedCrawler] start intent=%s direct=%d queries=%d",
            plan.intent.value,
            len(direct),
            len(queries),
        )

        web_results: list[WebSearchResult] = []
        seen_urls: set[str] = {c.landing_url or "" for c in direct}
        for query in queries:
            if len(web_results) >= self.web_cfg.max_total_results:
                break
            results = await self.search_engine.search(query, limit=self.web_cfg.max_results_per_query)
            for result in results:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                web_results.append(result)
                if len(web_results) >= self.web_cfg.max_total_results:
                    break

        candidates = list(direct)
        for result in web_results[: self.crawler_cfg.max_pages]:
            candidate = await self._candidate_from_web_result(result)
            if candidate:
                candidates.append(candidate)

        logger.debug(
            "[PaperOS][TargetedCrawler] done direct=%d pages=%d candidates=%d",
            len(direct),
            len(web_results),
            len(candidates),
        )
        return candidates

    def _direct_candidates(self, plan: SearchPlan) -> list[PaperCandidate]:
        out: list[PaperCandidate] = []
        for hyp in plan.hypotheses:
            if hyp.arxiv_id:
                arxiv_id = extract_arxiv_id(hyp.arxiv_id) or hyp.arxiv_id
                url = f"https://arxiv.org/abs/{arxiv_id}"
                cand = self.domain_resolver.candidate_from_known_url(url)
                if cand:
                    cand.title = hyp.title or hyp.translated_title or cand.title
                    cand.authors = hyp.authors or cand.authors
                    cand.year = hyp.year or cand.year
                    cand.venue = hyp.venue or cand.venue
                    out.append(cand)
            if hyp.url and looks_like_http_url(hyp.url):
                cand = self.domain_resolver.candidate_from_known_url(hyp.url)
                if cand:
                    cand.title = hyp.title or hyp.translated_title or cand.title
                    out.append(cand)
        return out

    def _build_queries(self, plan: SearchPlan) -> list[str]:
        queries: list[str] = []
        for hyp in plan.hypotheses:
            for query in hyp.search_queries:
                self._append_query(queries, query)
            if hyp.doi:
                self._append_query(queries, f'"{hyp.doi}" pdf')
            if hyp.title:
                self._append_query(queries, f'"{hyp.title}" pdf')
            if hyp.translated_title and hyp.translated_title != hyp.title:
                self._append_query(queries, f'"{hyp.translated_title}" pdf')
            if hyp.arxiv_id:
                self._append_query(queries, f"arxiv {hyp.arxiv_id}")
            if hyp.kind == HypothesisKind.TOPIC:
                base = hyp.translated_title or hyp.title or " ".join(hyp.search_queries) or plan.translated_query or plan.raw_query
                self._append_query(queries, f"{base} foundational paper pdf")
                self._append_query(queries, f"{base} survey important papers")
                self._append_query(queries, f"site:arxiv.org {base}")
                self._append_query(queries, f"site:openreview.net {base}")
        if not queries:
            base = plan.translated_query or plan.raw_query
            suffix = "foundational papers" if plan.intent == SearchIntent.TOPIC_DISCOVERY else "pdf"
            self._append_query(queries, f"{base} {suffix}")
        return queries[: max(1, plan.max_candidates)]

    def _append_query(self, queries: list[str], query: str | None) -> None:
        if not query:
            return
        query = re.sub(r"\s+", " ", query).strip()
        if query and query not in queries:
            queries.append(query)

    async def _candidate_from_web_result(self, result: WebSearchResult) -> PaperCandidate | None:
        url = canonical_url(result.url)
        direct_locations = self.domain_resolver.fulltext_from_url(url, source=result.source)
        candidate = PaperCandidate(
            title=strip_html(result.title) or url,
            abstract=strip_html(result.snippet) or None,
            landing_url=url,
            download_url=direct_locations[0].url if direct_locations else None,
            fulltext_locations=direct_locations,
            arxiv_id=extract_arxiv_id(url),
            doi=extract_doi(url + " " + result.snippet),
            source=result.source,
            raw={"web_result": result.__dict__},
        )
        if looks_like_pdf_url(url):
            logger.debug("[PaperOS][TargetedCrawler] direct_pdf_result url=%s", url)
            return candidate

        html_data = await self._fetch_html(url)
        if not html_data:
            return candidate
        self._merge_html_metadata(candidate, html_data, base_url=url)
        logger.debug(
            "[PaperOS][TargetedCrawler] crawled host=%s title=%s pdf_candidates=%d",
            host_of(url),
            self._short(candidate.title),
            len(candidate.fulltext_locations),
        )
        return candidate

    async def _fetch_html(self, url: str) -> ExtractedHTML | None:
        try:
            async with self._client.stream("GET", url) as resp:
                if resp.status_code in {401, 403}:
                    logger.debug("[PaperOS][TargetedCrawler] auth_required url=%s status=%d", url, resp.status_code)
                    return None
                if resp.status_code >= 400:
                    logger.debug("[PaperOS][TargetedCrawler] http_skip url=%s status=%d", url, resp.status_code)
                    return None
                content_type = resp.headers.get("content-type", "").lower()
                if "pdf" in content_type:
                    return None
                if "html" not in content_type and "text/" not in content_type and content_type:
                    return None
                data = bytearray()
                async for chunk in resp.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self.crawler_cfg.max_html_bytes:
                        logger.debug("[PaperOS][TargetedCrawler] html_too_large url=%s", url)
                        return None
            text = bytes(data).decode("utf-8", errors="ignore")
            return parse_paper_html(text, base_url=str(resp.url))
        except httpx.HTTPError as exc:
            logger.debug("[PaperOS][TargetedCrawler] fetch_failed url=%s error=%r", url, exc)
            return None

    def _merge_html_metadata(self, candidate: PaperCandidate, data: ExtractedHTML, *, base_url: str) -> None:
        title = data.first_meta("citation_title", "dc.title", "og:title", "twitter:title") or data.title
        if title:
            candidate.title = self._clean_title(title)
        authors = data.all_meta("citation_author", "dc.creator")
        if authors:
            candidate.authors = authors
        candidate.doi = candidate.doi or data.first_meta("citation_doi", "dc.identifier") or extract_doi(" ".join(data.all_meta("dc.identifier", "citation_doi")))
        candidate.abstract = candidate.abstract or data.first_meta("citation_abstract", "description", "og:description", "twitter:description")
        candidate.venue = candidate.venue or data.first_meta("citation_conference_title", "citation_journal_title", "citation_inbook_title")
        candidate.year = candidate.year or self._extract_year(data)
        candidate.arxiv_id = candidate.arxiv_id or extract_arxiv_id(base_url + " " + (candidate.doi or ""))

        pdf_urls: list[str] = []
        pdf_urls.extend(data.all_meta("citation_pdf_url"))
        for link in data.links:
            if len(pdf_urls) >= self.crawler_cfg.max_pdf_links_per_page:
                break
            if looks_like_pdf_url(link) or self.domain_resolver.fulltext_from_url(link, source="html_link"):
                pdf_urls.append(link)

        existing = {loc.url for loc in candidate.fulltext_locations}
        for pdf_url in pdf_urls:
            pdf_url = canonical_url(pdf_url, base_url=base_url)
            locations = self.domain_resolver.fulltext_from_url(pdf_url, source="html_meta_or_link")
            if not locations and looks_like_pdf_url(pdf_url):
                locations = [
                    FulltextLocation(
                        url=pdf_url,
                        source="html_meta_or_link",
                        kind="pdf",
                        confidence=0.78,
                        reason="extracted PDF URL from citation meta or href",
                    )
                ]
            for loc in locations:
                if loc.url not in existing:
                    existing.add(loc.url)
                    candidate.fulltext_locations.append(loc)
        candidate.fulltext_locations.sort(key=lambda loc: loc.confidence, reverse=True)
        if candidate.fulltext_locations and not candidate.download_url:
            candidate.download_url = candidate.fulltext_locations[0].url

    def _extract_year(self, data: ExtractedHTML) -> int | None:
        value = data.first_meta("citation_publication_date", "citation_date", "dc.date", "citation_year")
        if not value:
            return None
        match = re.search(r"(19|20)\d{2}", value)
        if not match:
            return None
        return int(match.group(0))

    def _clean_title(self, title: str) -> str:
        title = strip_html(title)
        # Search result titles often append site names. Keep this conservative.
        for sep in [" | arXiv", " - arXiv", " | OpenReview", " - ACL Anthology"]:
            if sep.lower() in title.lower():
                title = re.split(re.escape(sep), title, flags=re.I)[0].strip()
        return title

    def _short(self, text: str, limit: int = 70) -> str:
        return text if len(text) <= limit else text[: limit - 3] + "..."

    async def aclose(self) -> None:
        await self._client.aclose()
        await self.search_engine.aclose()
