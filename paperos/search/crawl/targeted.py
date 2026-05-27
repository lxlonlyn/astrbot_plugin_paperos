from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx
from astrbot.api import logger

from ...config import CrawlerConfig
from ..models import FulltextLocation, HypothesisKind, PaperCandidate, SearchPlan
from .domain_resolver import DomainResolver
from .html import ExtractedHTML, parse_paper_html
from .url_tools import (
    canonical_url,
    doi_landing_url,
    extract_arxiv_id,
    extract_doi,
    extract_urls,
    host_of,
    looks_like_http_url,
    looks_like_pdf_url,
    strip_html,
)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class TargetedPaperCrawler:
    """On-demand crawler for concrete paper sources.

    This class deliberately does not call a generic web-search backend. It only
    follows sources already present in SearchPlan: arXiv IDs, DOI landing URLs,
    direct URLs, OpenReview/ACL/CVF/PMLR pages, and direct PDFs.
    """

    def __init__(
        self,
        *,
        crawler_cfg: CrawlerConfig,
        domain_resolver: DomainResolver | None = None,
    ):
        self.crawler_cfg = crawler_cfg
        self.domain_resolver = domain_resolver or DomainResolver()
        self._client = httpx.AsyncClient(
            timeout=crawler_cfg.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": crawler_cfg.user_agent,
                "Accept": "text/html,application/pdf,*/*;q=0.5",
            },
        )

    async def discover(self, plan: SearchPlan) -> list[PaperCandidate]:
        if not self.crawler_cfg.enabled:
            logger.debug("[PaperOS][TargetedCrawler] disabled")
            return []

        candidates = self._direct_candidates(plan)
        if len(candidates) < plan.max_candidates:
            candidates.extend(await self._site_lookup_candidates(plan, seen=candidates))
        logger.debug(
            "[PaperOS][TargetedCrawler] start intent=%s direct_candidates=%d",
            plan.intent.value,
            len(candidates),
        )

        enriched: list[PaperCandidate] = []
        for candidate in candidates[: self.crawler_cfg.max_known_urls]:
            await self._enrich_candidate(candidate)
            enriched.append(candidate)

        logger.debug(
            "[PaperOS][TargetedCrawler] done direct=%d enriched=%d",
            len(candidates),
            len(enriched),
        )
        return enriched

    def _direct_candidates(self, plan: SearchPlan) -> list[PaperCandidate]:
        out: list[PaperCandidate] = []
        seen_keys: set[str] = set()

        for hyp in plan.hypotheses:
            for candidate in self._candidates_from_hypothesis(hyp):
                key = self._candidate_key(candidate)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                out.append(candidate)

        return out

    async def _site_lookup_candidates(
        self,
        plan: SearchPlan,
        *,
        seen: list[PaperCandidate],
    ) -> list[PaperCandidate]:
        """Look up precise titles on known scholarly sites.

        This is intentionally not a generic search backend. It only uses titles
        that the user or QueryAnalyzer has already made concrete, and it limits
        each site to a handful of candidates.
        """

        out: list[PaperCandidate] = []
        seen_keys = {self._candidate_key(candidate) for candidate in seen}
        titles = self._lookup_titles(plan)
        for title in titles:
            for candidate in await self._lookup_arxiv_title(title):
                self._append_unique(out, seen_keys, candidate)
            for candidate in await self._lookup_acm_title(title):
                self._append_unique(out, seen_keys, candidate)
            if len(out) >= plan.max_candidates:
                break
        if out:
            logger.debug("[PaperOS][TargetedCrawler] site_lookup titles=%d candidates=%d", len(titles), len(out))
        return out[: plan.max_candidates]

    def _lookup_titles(self, plan: SearchPlan) -> list[str]:
        titles: list[str] = []
        for hyp in plan.hypotheses:
            if hyp.kind not in {
                HypothesisKind.TITLE,
                HypothesisKind.FUZZY_TITLE,
                HypothesisKind.AUTHOR_VENUE_YEAR,
            }:
                continue
            for title in (hyp.translated_title, hyp.title):
                clean = strip_html(title or "")
                if len(clean) >= 8 and clean.lower() not in {item.lower() for item in titles}:
                    titles.append(clean)
        return titles[: self.crawler_cfg.max_known_urls]

    async def _lookup_arxiv_title(self, title: str) -> list[PaperCandidate]:
        query = quote_plus(f'ti:"{title}"')
        url = (
            "https://export.arxiv.org/api/query"
            f"?search_query={query}&start=0&max_results={self.crawler_cfg.max_site_lookup_results}"
        )
        try:
            resp = await self._client.get(url, headers={"Accept": "application/atom+xml,*/*;q=0.5"})
            if resp.status_code >= 400:
                logger.debug("[PaperOS][TargetedCrawler] arxiv_lookup_skip status=%d title=%s", resp.status_code, title)
                return []
            return self._parse_arxiv_feed(resp.text, query_title=title)
        except (httpx.HTTPError, ET.ParseError) as exc:
            logger.debug("[PaperOS][TargetedCrawler] arxiv_lookup_failed title=%s error=%r", title, exc)
            return []

    def _parse_arxiv_feed(self, text: str, *, query_title: str) -> list[PaperCandidate]:
        root = ET.fromstring(text)
        out: list[PaperCandidate] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            entry_title = self._xml_text(entry, "atom:title")
            arxiv_id = extract_arxiv_id(self._xml_text(entry, "atom:id"))
            if not entry_title or not arxiv_id:
                continue
            if not self._is_plausible_title_match(query_title, entry_title):
                continue
            published = self._xml_text(entry, "atom:published")
            authors = [
                self._xml_text(author, "atom:name")
                for author in entry.findall("atom:author", ATOM_NS)
                if self._xml_text(author, "atom:name")
            ]
            candidate = self.domain_resolver.candidate_from_known_url(
                f"https://arxiv.org/abs/{arxiv_id}",
                source="arxiv_title_lookup",
            )
            if not candidate:
                continue
            candidate.title = self._clean_title(entry_title)
            candidate.authors = authors
            candidate.abstract = self._xml_text(entry, "atom:summary") or None
            candidate.year = int(published[:4]) if published[:4].isdigit() else None
            candidate.source = "arxiv_title_lookup"
            candidate.raw["query_title"] = query_title
            out.append(candidate)
        return out

    async def _lookup_acm_title(self, title: str) -> list[PaperCandidate]:
        url = (
            "https://dl.acm.org/action/doSearch"
            f"?AllField={quote_plus(title)}&pageSize={self.crawler_cfg.max_site_lookup_results}"
        )
        html_data = await self._fetch_html(url)
        if not html_data:
            return []

        out: list[PaperCandidate] = []
        seen_links: set[str] = set()
        for link in html_data.links:
            if len(out) >= self.crawler_cfg.max_site_lookup_results:
                break
            if "dl.acm.org/doi/" not in link:
                continue
            link = canonical_url(link)
            if link in seen_links:
                continue
            seen_links.add(link)
            candidate = self.domain_resolver.candidate_from_known_url(link, source="acm_title_lookup")
            if not candidate:
                continue
            candidate.source = "acm_title_lookup"
            candidate.raw["query_title"] = title
            await self._enrich_candidate(candidate)
            if self._is_plausible_title_match(title, candidate.title):
                out.append(candidate)
        return out

    def _xml_text(self, item: ET.Element, path: str) -> str:
        found = item.find(path, ATOM_NS)
        return re.sub(r"\s+", " ", (found.text or "")).strip() if found is not None else ""

    def _append_unique(
        self,
        out: list[PaperCandidate],
        seen_keys: set[str],
        candidate: PaperCandidate,
    ) -> None:
        key = self._candidate_key(candidate)
        if key not in seen_keys:
            seen_keys.add(key)
            out.append(candidate)

    def _is_plausible_title_match(self, expected: str, actual: str) -> bool:
        expected_tokens = set(self._title_tokens(expected))
        actual_tokens = set(self._title_tokens(actual))
        if not expected_tokens or not actual_tokens:
            return False
        overlap = len(expected_tokens & actual_tokens) / max(1, len(expected_tokens))
        return overlap >= 0.72

    def _candidates_from_hypothesis(self, hyp) -> list[PaperCandidate]:
        out: list[PaperCandidate] = []

        if hyp.arxiv_id:
            arxiv_id = extract_arxiv_id(hyp.arxiv_id) or hyp.arxiv_id
            cand = self.domain_resolver.candidate_from_known_url(
                f"https://arxiv.org/abs/{arxiv_id}", source="llm_arxiv_id"
            )
            if cand:
                self._apply_hypothesis_metadata(cand, hyp)
                out.append(cand)

        if hyp.doi:
            doi = extract_doi(hyp.doi) or hyp.doi.strip()
            if doi.lower().startswith("10.1145/"):
                cand = self.domain_resolver.candidate_from_known_url(
                    f"https://dl.acm.org/doi/{doi}",
                    source="llm_acm_doi",
                ) or PaperCandidate(title=hyp.title or hyp.translated_title or doi, doi=doi)
            else:
                cand = PaperCandidate(
                    title=hyp.title or hyp.translated_title or doi,
                    authors=list(hyp.authors),
                    year=hyp.year,
                    venue=hyp.venue,
                    doi=doi,
                    landing_url=doi_landing_url(doi),
                    source="llm_doi",
                    raw={"hypothesis_note": hyp.note},
                )
            self._apply_hypothesis_metadata(cand, hyp)
            out.append(cand)

        if hyp.url and looks_like_http_url(hyp.url):
            cand = self.domain_resolver.candidate_from_known_url(hyp.url, source="llm_url")
            if cand:
                self._apply_hypothesis_metadata(cand, hyp)
                out.append(cand)

        # Some LLMs put concrete URLs inside search_queries even though this
        # corrected pipeline no longer treats them as search queries.
        for text in list(hyp.search_queries or []):
            for url in extract_urls(text):
                cand = self.domain_resolver.candidate_from_known_url(url, source="llm_query_url")
                if cand:
                    self._apply_hypothesis_metadata(cand, hyp)
                    out.append(cand)
            arxiv_id = extract_arxiv_id(text)
            if arxiv_id and hyp.kind in {HypothesisKind.ARXIV, HypothesisKind.TITLE, HypothesisKind.FUZZY_TITLE, HypothesisKind.TOPIC}:
                cand = self.domain_resolver.candidate_from_known_url(
                    f"https://arxiv.org/abs/{arxiv_id}", source="llm_query_arxiv"
                )
                if cand:
                    self._apply_hypothesis_metadata(cand, hyp)
                    out.append(cand)

        return out

    def _apply_hypothesis_metadata(self, cand: PaperCandidate, hyp) -> None:
        if hyp.title or hyp.translated_title:
            cand.title = hyp.title or hyp.translated_title or cand.title
        cand.authors = hyp.authors or cand.authors
        cand.year = hyp.year or cand.year
        cand.venue = hyp.venue or cand.venue
        cand.doi = cand.doi or hyp.doi
        cand.arxiv_id = cand.arxiv_id or hyp.arxiv_id
        cand.raw.setdefault("hypothesis_note", hyp.note)

    async def _enrich_candidate(self, candidate: PaperCandidate) -> None:
        url = candidate.landing_url or candidate.download_url
        if not url or not looks_like_http_url(url):
            logger.debug(
                "[PaperOS][TargetedCrawler] skip_no_url title=%s source=%s",
                self._short(candidate.title),
                candidate.source,
            )
            return

        # Direct PDF candidates do not need HTML crawling.
        if looks_like_pdf_url(url):
            self._add_fulltext_locations(candidate, self.domain_resolver.fulltext_from_url(url, source=candidate.source))
            return

        html_data = await self._fetch_html(url)
        if not html_data:
            return

        self._merge_html_metadata(candidate, html_data, base_url=url)

    async def _fetch_html(self, url: str) -> ExtractedHTML | None:
        try:
            async with self._client.stream("GET", url) as resp:
                if resp.status_code in {401, 403}:
                    logger.debug(
                        "[PaperOS][TargetedCrawler] auth_required url=%s status=%d",
                        url,
                        resp.status_code,
                    )
                    return None
                if resp.status_code >= 400:
                    logger.debug(
                        "[PaperOS][TargetedCrawler] http_skip url=%s status=%d",
                        url,
                        resp.status_code,
                    )
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

                final_url = str(resp.url)
                text = bytes(data).decode("utf-8", errors="ignore")
                logger.debug(
                    "[PaperOS][TargetedCrawler] fetched host=%s bytes=%d final=%s",
                    host_of(final_url),
                    len(data),
                    final_url,
                )
                return parse_paper_html(text, base_url=final_url)
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

        candidate.doi = (
            candidate.doi
            or data.first_meta("citation_doi", "dc.identifier")
            or extract_doi(" ".join(data.all_meta("dc.identifier", "citation_doi")))
        )
        candidate.abstract = candidate.abstract or data.first_meta(
            "citation_abstract", "description", "og:description", "twitter:description"
        )
        candidate.venue = candidate.venue or data.first_meta(
            "citation_conference_title", "citation_journal_title", "citation_inbook_title"
        )
        candidate.year = candidate.year or self._extract_year(data)
        candidate.arxiv_id = candidate.arxiv_id or extract_arxiv_id(base_url + " " + (candidate.doi or ""))

        pdf_urls: list[str] = []
        pdf_urls.extend(data.all_meta("citation_pdf_url"))
        for link in data.links:
            if len(pdf_urls) >= self.crawler_cfg.max_pdf_links_per_page:
                break
            if looks_like_pdf_url(link) or self.domain_resolver.fulltext_from_url(link, source="html_link"):
                pdf_urls.append(link)

        new_locations: list[FulltextLocation] = []
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
            new_locations.extend(locations)

        self._add_fulltext_locations(candidate, new_locations)
        logger.debug(
            "[PaperOS][TargetedCrawler] enriched host=%s title=%s pdf_candidates=%d",
            host_of(base_url),
            self._short(candidate.title),
            len(candidate.fulltext_locations),
        )

    def _add_fulltext_locations(self, candidate: PaperCandidate, locations: list[FulltextLocation]) -> None:
        existing = {loc.url for loc in candidate.fulltext_locations}
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
        return int(match.group(0)) if match else None

    def _clean_title(self, title: str) -> str:
        title = strip_html(title)
        for sep in [" | arXiv", " - arXiv", " | OpenReview", " - ACL Anthology"]:
            if sep.lower() in title.lower():
                title = re.split(re.escape(sep), title, flags=re.I)[0].strip()
        return title

    def _title_tokens(self, title: str) -> list[str]:
        normalized = re.sub(r"[^\w\s]", " ", strip_html(title).lower())
        return [token for token in normalized.split() if len(token) > 2]

    def _candidate_key(self, candidate: PaperCandidate) -> str:
        if candidate.doi:
            return "doi:" + candidate.doi.lower()
        if candidate.arxiv_id:
            return "arxiv:" + candidate.arxiv_id.lower()
        return "url:" + (candidate.landing_url or candidate.download_url or candidate.title).lower()

    def _short(self, text: str, limit: int = 70) -> str:
        return text if len(text) <= limit else text[: limit - 3] + "..."

    async def aclose(self) -> None:
        await self._client.aclose()
