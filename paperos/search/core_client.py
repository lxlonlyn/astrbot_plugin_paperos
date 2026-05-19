from __future__ import annotations

from typing import Any

import httpx
from astrbot.api import logger

from ..config import CoreAPIConfig
from .models import PaperCandidate


class CoreAPIError(RuntimeError):
    pass


class CoreClient:
    """Small async client for CORE API v3.

    Keep this class boring: no ranking, no business policy, only HTTP + parsing.
    """

    def __init__(self, cfg: CoreAPIConfig):
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        return headers

    async def search_works(self, q: str, *, limit: int, offset: int = 0, sort: str | None = None) -> list[PaperCandidate]:
        if not self.cfg.enabled:
            return []

        url = f"{self.base_url}/search/works/"  # trailing slash matters for GET paths
        params = {
            "q": q,
            "limit": max(1, min(limit, 100)),
            "offset": max(0, offset),
            "sort": sort or self.cfg.sort or "relevance",
        }

        logger.debug("prepare to send: {}, params: {}".format(url, params))

        async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
            resp = await client.get(url, params=params, headers=self._headers())

        if resp.status_code >= 400:
            raise CoreAPIError(f"CORE API error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        return [self._parse_work(item) for item in results if isinstance(item, dict)]

    async def get_work(self, core_id: str) -> PaperCandidate | None:
        if not self.cfg.enabled or not core_id:
            return None

        url = f"{self.base_url}/works/{core_id}"
        async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
            resp = await client.get(url, headers=self._headers())

        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CoreAPIError(f"CORE API error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return self._parse_work(data) if isinstance(data, dict) else None

    def _parse_work(self, item: dict[str, Any]) -> PaperCandidate:
        authors_raw = item.get("authors") or item.get("contributors") or []
        authors: list[str] = []
        if isinstance(authors_raw, list):
            for a in authors_raw:
                if isinstance(a, dict):
                    name = a.get("name") or a.get("fullName")
                    if name:
                        authors.append(str(name))
                elif isinstance(a, str):
                    authors.append(a)

        links = item.get("links") if isinstance(item.get("links"), list) else []
        link_url = None
        if links is not None:
            for link in links:
                if isinstance(link, dict) and link.get("url"):
                    link_url = str(link["url"])
                    break

        year = item.get("yearPublished") or item.get("publishedYear") or item.get("year")
        try:
            year = int(year) if year is not None else None
        except (TypeError, ValueError):
            year = None

        core_id = item.get("id") or item.get("coreId")
        return PaperCandidate(
            title=str(item.get("title") or "").strip(),
            authors=authors,
            year=year,
            venue=item.get("publisher") or item.get("journals") or item.get("dataProviders"),
            abstract=item.get("abstract"),
            doi=(str(item.get("doi")).lower() if item.get("doi") else None),
            arxiv_id=(str(item.get("arxivId")) if item.get("arxivId") else None),
            core_id=(str(core_id) if core_id is not None else None),
            download_url=item.get("downloadUrl") or link_url,
            landing_url=item.get("sourceFulltextUrls", [None])[0] if isinstance(item.get("sourceFulltextUrls"), list) and item.get("sourceFulltextUrls") else None,
            citation_count=item.get("citationCount") if isinstance(item.get("citationCount"), int) else None,
            source="core",
            raw=item,
        )
