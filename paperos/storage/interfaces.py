from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .models import ChunkRecord, PaperRecordDraft
from .objects import StoredObject


class LocalPaperRepository(Protocol):
    """Local PaperOS metadata store.

    The repository is storage-facing and must not import `paperos.search`.
    Search-stage candidates should be converted to PaperRecordDraft by a facade
    or adapter before they enter storage.
    """

    async def initialize(self) -> None: ...

    async def find_by_identifier(self, *, doi: str | None = None, arxiv_id: str | None = None) -> PaperRecordDraft | None: ...

    async def search_by_title(self, title: str, *, limit: int = 10) -> list[PaperRecordDraft]: ...

    async def exists(self, draft: PaperRecordDraft) -> bool: ...

    async def find_paper_id_for_draft(self, draft: PaperRecordDraft) -> str | None: ...

    async def upsert_paper(
        self,
        draft: PaperRecordDraft,
        *,
        source_query: str | None = None,
        decision: str = "search_selected",
        message: str | None = None,
    ) -> str: ...

    async def register_object(self, stored: StoredObject) -> str: ...

    async def attach_object_to_current_version(self, *, paper_id: str, object_id: str, role: str = "pdf") -> None: ...

    async def attach_object_to_fulltext_location(
        self,
        *,
        paper_id: str,
        url: str,
        object_id: str,
    ) -> None: ...

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

    async def mark_job_done(self, job_id: str) -> None: ...

    async def mark_job_failed_final(self, job_id: str, error_message: str) -> None: ...

    async def current_version_id(self, paper_id: str) -> str | None: ...

    async def persist_document_processing_result(
        self,
        **kwargs: Any,
    ) -> str: ...

    async def search_chunks_fts(
        self,
        query: str,
        *,
        paper_id: str | None = None,
        limit: int = 20,
    ) -> list[ChunkRecord]: ...

    async def get_chunks_by_ids(self, ids: list[str]) -> list[ChunkRecord]: ...

    async def get_neighbor_chunks(
        self,
        chunk_id: str,
        *,
        before: int = 1,
        after: int = 1,
    ) -> list[ChunkRecord]: ...

    async def get_paper_citation_metadata(self, paper_id: str) -> dict[str, Any]: ...

    async def get_chunks_for_parser_run(self, parser_run_id: str) -> list[ChunkRecord]: ...

    async def get_chunks_for_paper(self, paper_id: str) -> list[ChunkRecord]: ...

    async def update_index_status(
        self,
        *,
        paper_id: str,
        index_name: str,
        status: str,
        profile: str | None = None,
        message: str | None = None,
    ) -> None: ...


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
