from __future__ import annotations

from typing import Protocol

from paperos.search.models import PaperCandidate


class LocalPaperRepository(Protocol):
    """Future local database interface.

    The search service can depend on this Protocol later, without caring whether
    the implementation is SQLite, LanceDB, or a hybrid index.
    """

    async def find_by_identifier(self, *, doi: str | None = None, arxiv_id: str | None = None) -> PaperCandidate | None:
        ...

    async def search_by_title(self, title: str, *, limit: int = 10) -> list[PaperCandidate]:
        ...

    async def exists(self, candidate: PaperCandidate) -> bool:
        ...
