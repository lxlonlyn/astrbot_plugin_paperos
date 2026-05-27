from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import urlencode

import httpx
from astrbot.api import logger

from ...config import WebSearchConfig
from ..models import WebSearchResult
from .url_tools import canonical_url, strip_html


class WebSearchEngine(Protocol):
    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]: ...

    async def aclose(self) -> None: ...


class DuckDuckGoHTMLSearchEngine:
    """Small web-search adapter based on DuckDuckGo's HTML endpoint.

    This is not meant to be a large-scale crawler. It is a pragmatic default for
    on-demand personal use. If deployment needs another search provider, replace
    this class behind the same interface instead of changing the pipeline.
    """

    _RESULT_RE = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.I | re.S,
    )
    _SNIPPET_RE = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>', re.I | re.S)

    def __init__(self, cfg: WebSearchConfig):
        self.cfg = cfg
        self._client = httpx.AsyncClient(
            timeout=cfg.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": cfg.user_agent, "Accept": "text/html,*/*;q=0.5"},
        )

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        if not self.cfg.enabled:
            return []
        limit = max(1, min(limit, self.cfg.max_results_per_query))
        params = {"q": query}
        url = self.cfg.endpoint
        logger.debug("[PaperOS][WebSearch] query=%r limit=%d", query, limit)
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("[PaperOS][WebSearch] failed query=%r error=%r", query, exc)
            return []

        html = resp.text
        snippets = [strip_html(m.group("snippet")) for m in self._SNIPPET_RE.finditer(html)]
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        for idx, match in enumerate(self._RESULT_RE.finditer(html), 1):
            target = canonical_url(match.group("href"))
            if not target or target in seen:
                continue
            seen.add(target)
            results.append(
                WebSearchResult(
                    url=target,
                    title=strip_html(match.group("title")),
                    snippet=snippets[len(results)] if len(results) < len(snippets) else "",
                    source="duckduckgo_html",
                    rank=idx,
                    query=query,
                )
            )
            if len(results) >= limit:
                break
        logger.debug("[PaperOS][WebSearch] query=%r returned=%d", query, len(results))
        return results

    async def aclose(self) -> None:
        await self._client.aclose()


def encode_query_for_log(query: str) -> str:
    return urlencode({"q": query})
