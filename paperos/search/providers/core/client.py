from __future__ import annotations

from typing import Any

import httpx
from astrbot.api import logger

from ....config import CoreAPIConfig
from ...models import PaperCandidate


class CoreAPIError(RuntimeError):
    pass


class CoreClient:
    def __init__(self, cfg: CoreAPIConfig):
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        return headers

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.cfg.timeout_seconds, follow_redirects=True)
        return self._client

    async def search_works(self, q: str, *, limit: int, offset: int = 0, sort: str | None = None) -> list[PaperCandidate]:
        if not self.cfg.enabled:
            return []
        url = f"{self.base_url}/search/works/"
        params = {
            "q": q,
            "limit": max(1, min(int(limit), 100)),
            "offset": max(0, int(offset)),
            "sort": sort or self.cfg.sort or "relevance",
        }
        logger.debug("[PaperOS][CORE] GET %s params=%s", url, params)
        resp = await self._http().get(url, params=params, headers=self._headers())
        if resp.status_code >= 400:
            raise CoreAPIError(f"CORE search failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        results = data.get("results") or []
        if not isinstance(results, list):
            return []
        return [self._work_to_candidate(x) for x in results if isinstance(x, dict)]

    async def get_work(self, core_id: str) -> PaperCandidate | None:
        url = f"{self.base_url}/works/{core_id}"
        resp = await self._http().get(url, headers=self._headers())
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CoreAPIError(f"CORE get_work failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        return self._work_to_candidate(data) if isinstance(data, dict) else None

    def _work_to_candidate(self, work: dict[str, Any]) -> PaperCandidate:
        authors = self._authors(work.get("authors"))
        title = self._first_str(work.get("title")) or self._first_str(work.get("name")) or ""
        doi = self._first_str(work.get("doi"))
        download_url = self._first_str(work.get("downloadUrl")) or self._first_str(work.get("download_url"))
        landing_url = (
            self._first_str(work.get("sourceFulltextUrls"))
            or self._first_str(work.get("publisherLink"))
            or self._first_str(work.get("links"))
        )
        return PaperCandidate(
            title=title,
            authors=authors,
            year=self._safe_int(work.get("yearPublished") or work.get("publishedYear") or work.get("year")),
            venue=self._first_str(work.get("journals")) or self._first_str(work.get("publisher")) or self._first_str(work.get("repositoryDocument")),
            publisher=self._first_str(work.get("publisher")),
            abstract=self._first_str(work.get("abstract")),
            doi=doi,
            arxiv_id=self._first_str(work.get("arxivId")) or self._extract_arxiv_from_doi(doi),
            core_id=str(work.get("id")) if work.get("id") is not None else None,
            citation_count=self._safe_int(work.get("citationCount") or work.get("citationsCount")),
            download_url=download_url,
            landing_url=landing_url,
            source="core",
            raw=work,
        )

    def _authors(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    out.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("fullName") or item.get("displayName")
                if name:
                    out.append(str(name).strip())
        return out

    def _first_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, list):
            for x in value:
                s = self._first_str(x)
                if s:
                    return s
            return None
        if isinstance(value, dict):
            for key in ("url", "name", "title", "value", "link"):
                if key in value:
                    s = self._first_str(value[key])
                    if s:
                        return s
        return None

    def _safe_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    def _extract_arxiv_from_doi(self, doi: str | None) -> str | None:
        if not doi:
            return None
        low = doi.lower()
        marker = "10.48550/arxiv."
        if marker in low:
            return doi[low.index(marker) + len(marker):]
        return None
