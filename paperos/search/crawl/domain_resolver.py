from __future__ import annotations

from urllib.parse import urlparse

from astrbot.api import logger

from ..models import FulltextLocation, PaperCandidate
from .url_tools import (
    acl_pdf_url,
    arxiv_pdf_url,
    canonical_url,
    extract_arxiv_id,
    host_of,
    looks_like_pdf_url,
    openreview_pdf_url,
)


class DomainResolver:
    """Domain-specific URL normalizer used by targeted crawler.

    This layer is deliberately small. It only creates fulltext candidates; the
    verifier still decides whether a candidate is actually a PDF.
    """

    def fulltext_from_url(self, url: str, *, source: str = "domain") -> list[FulltextLocation]:
        url = canonical_url(url)
        host = host_of(url)
        out: list[FulltextLocation] = []

        arxiv_id = extract_arxiv_id(url)
        if arxiv_id and (host.endswith("arxiv.org") or "arxiv" in url.lower()):
            out.append(
                FulltextLocation(
                    url=arxiv_pdf_url(arxiv_id),
                    source="arxiv",
                    kind="pdf",
                    confidence=0.98,
                    host_type="preprint",
                    reason="normalized arXiv identifier to direct PDF URL",
                )
            )

        openreview_pdf = openreview_pdf_url(url)
        if openreview_pdf:
            out.append(
                FulltextLocation(
                    url=openreview_pdf,
                    source="openreview",
                    kind="pdf",
                    confidence=0.94,
                    host_type="conference_openreview",
                    reason="normalized OpenReview forum URL to PDF endpoint",
                )
            )

        acl_pdf = acl_pdf_url(url)
        if acl_pdf:
            out.append(
                FulltextLocation(
                    url=acl_pdf,
                    source="acl_anthology",
                    kind="pdf",
                    confidence=0.93,
                    host_type="publisher_oa",
                    reason="normalized ACL Anthology paper URL to PDF URL",
                )
            )

        if looks_like_pdf_url(url):
            out.append(
                FulltextLocation(
                    url=url,
                    source=source,
                    kind="pdf",
                    confidence=0.80,
                    reason="URL path looks like a direct PDF",
                )
            )

        # Preserve order but deduplicate URLs.
        deduped: list[FulltextLocation] = []
        seen: set[str] = set()
        for loc in sorted(out, key=lambda item: item.confidence, reverse=True):
            if loc.url not in seen:
                seen.add(loc.url)
                deduped.append(loc)
        if deduped:
            logger.debug("[PaperOS][DomainResolver] url=%s locations=%d", url, len(deduped))
        return deduped

    def candidate_from_known_url(self, url: str) -> PaperCandidate | None:
        arxiv_id = extract_arxiv_id(url)
        if arxiv_id and "arxiv" in url.lower():
            return PaperCandidate(
                title=f"arXiv:{arxiv_id}",
                arxiv_id=arxiv_id,
                landing_url=url if "/abs/" in url else f"https://arxiv.org/abs/{arxiv_id}",
                fulltext_locations=self.fulltext_from_url(url, source="arxiv"),
                source="arxiv_url",
                raw={"source_url": url},
            )
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            locations = self.fulltext_from_url(url, source="known_url")
            if locations:
                return PaperCandidate(
                    title=url,
                    landing_url=url,
                    fulltext_locations=locations,
                    source="known_url",
                    raw={"source_url": url},
                )
        return None
