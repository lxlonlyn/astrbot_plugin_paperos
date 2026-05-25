from __future__ import annotations

from astrbot.api import logger

from ..base import FulltextProvider
from ...models import FulltextLocation, PaperCandidate
from .client import CoreAPIError, CoreClient


class CoreFulltextProvider(FulltextProvider):
    name = "core"

    def __init__(self, client: CoreClient):
        self.client = client

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        locations: list[FulltextLocation] = []

        # 1. Use explicit CORE downloadUrl/link if present on the Work object.
        # Do not use landing/sourceFulltextUrls such as arxiv.org/abs/... here:
        # those are not direct fulltext PDF candidates.
        if paper.download_url:
            locations.append(
                FulltextLocation(
                    url=paper.download_url,
                    source=self.name,
                    kind="pdf",
                    confidence=0.85,
                    reason="CORE work returned explicit downloadUrl/download link",
                    request_headers=self._headers_for(paper.download_url),
                )
            )

        # 2. Search CORE outputs and use CORE's own output download endpoint.
        # This is the provider-neutral way to get actual fulltext bytes from CORE.
        output_queries = self._build_output_queries(paper)
        for query in output_queries:
            try:
                outputs = await self.client.search_outputs(
                    query,
                    limit=3,
                    sort=self.client.cfg.sort,
                )
            except CoreAPIError as exc:
                logger.debug("[PaperOS][CoreFulltextProvider] output search failed q=%r error=%s", query, exc)
                continue

            logger.debug(
                "[PaperOS][CoreFulltextProvider] output_query=%r outputs=%d paper=%s",
                query,
                len(outputs),
                self._short(paper.title),
            )

            for output in outputs:
                output_id = self.client.output_id(output)
                explicit_download = self.client.output_download_url_from_object(output)

                if explicit_download:
                    locations.append(
                        FulltextLocation(
                            url=explicit_download,
                            source=self.name,
                            kind="pdf",
                            confidence=0.90,
                            reason=f"CORE output search returned explicit downloadUrl for output={output_id or '?'}",
                            request_headers=self._headers_for(explicit_download),
                        )
                    )

                if output_id:
                    locations.append(
                        FulltextLocation(
                            url=self.client.output_download_url(output_id),
                            source=self.name,
                            kind="pdf",
                            confidence=0.95,
                            reason=f"CORE output download endpoint output={output_id}",
                            request_headers=self.client.download_headers(),
                        )
                    )

            if locations:
                # Stop once one query found output candidates. The verifier will
                # download/validate in confidence order.
                break

        # Dedup by URL and keep highest-confidence location.
        dedup: dict[str, FulltextLocation] = {}
        for loc in locations:
            old = dedup.get(loc.url)
            if old is None or loc.confidence > old.confidence:
                dedup[loc.url] = loc

        return sorted(dedup.values(), key=lambda x: x.confidence, reverse=True)

    def _build_output_queries(self, paper: PaperCandidate) -> list[str]:
        queries: list[str] = []

        if paper.doi:
            queries.append(f'doi:"{paper.doi}"')

        if paper.arxiv_id:
            queries.append(f'arxivId:"{paper.arxiv_id}"')
            queries.append(f'doi:"10.48550/arXiv.{paper.arxiv_id}"')

        if paper.title:
            # This is less precise, so put it after DOI/arXiv.
            safe_title = paper.title.replace('"', " ")
            queries.append(f'title:"{safe_title}"')

        seen: set[str] = set()
        out: list[str] = []
        for q in queries:
            if q and q not in seen:
                seen.add(q)
                out.append(q)
        return out

    def _headers_for(self, url: str) -> dict[str, str]:
        # CORE API endpoints need the CORE Authorization header. Public direct
        # PDF URLs do not need it, but including Authorization only for CORE
        # domains avoids leaking tokens to third-party publishers.
        low = url.lower()
        if "core.ac.uk" in low or self.client.base_url.lower() in low:
            return self.client.download_headers()
        return {"Accept": "application/pdf,*/*;q=0.5"}

    def _short(self, title: str, limit: int = 70) -> str:
        return title if len(title) <= limit else title[: limit - 3] + "..."

    async def aclose(self):
        return None
