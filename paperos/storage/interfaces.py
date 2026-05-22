from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..search.models import PaperCandidate

from .objects import StoredObject


class LocalPaperRepository(Protocol):
    """Local PaperOS metadata store.

    Search-stage dedup is still handled by paperos.search.resolve.dedup. This
    repository performs persistent dedup across runs and records versions,
    objects, jobs and local indexes.
    """

    async def initialize(self) -> None: ...

    async def find_by_identifier(self, *, doi: str | None = None, arxiv_id: str | None = None) -> PaperCandidate | None: ...

    async def search_by_title(self, title: str, *, limit: int = 10) -> list[PaperCandidate]: ...

    async def exists(self, candidate: PaperCandidate) -> bool: ...

    async def find_paper_id_for_candidate(self, candidate: PaperCandidate) -> str | None: ...

    async def upsert_candidate(
        self,
        candidate: PaperCandidate,
        *,
        source_query: str | None = None,
        decision: str = "search_selected",
        message: str | None = None,
    ) -> str: ...

    async def register_object(self, stored: StoredObject) -> str: ...

    async def attach_object_to_current_version(self, *, paper_id: str, object_id: str, role: str = "pdf") -> None: ...

    async def enqueue_job(
        self,
        job_type: str,
        *,
        dedupe_key: str | None = None,
        paper_id: str | None = None,
        version_id: str | None = None,
        object_id: str | None = None,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        available_at: str | None = None,
    ) -> str: ...


class ObjectStore(Protocol):
    async def put_bytes(
        self,
        data: bytes,
        *,
        kind: str,
        suffix: str | None = None,
        mime_type: str | None = None,
        object_id: str | None = None,
    ) -> StoredObject: ...

    async def put_file(
        self,
        source_path: Path,
        *,
        kind: str,
        suffix: str | None = None,
        mime_type: str | None = None,
        object_id: str | None = None,
    ) -> StoredObject: ...

    def resolve_path(self, storage_key: str) -> Path: ...
