from __future__ import annotations

"""Deprecated compatibility module.

The corrected PaperOS search path intentionally has no generic web-search
backend. QueryAnalyzer proposes concrete sources; TargetedPaperCrawler follows
only those sources. This file remains as a harmless placeholder so stale imports
fail less destructively during migration. It should not be used by new code.
"""

from typing import Protocol

from ..models import WebSearchResult


class WebSearchEngine(Protocol):
    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]: ...
    async def aclose(self) -> None: ...
