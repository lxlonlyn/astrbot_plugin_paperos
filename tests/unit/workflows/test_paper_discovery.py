from __future__ import annotations

import asyncio

from paperos.search.models import FulltextLocation, FulltextStatus, PaperCandidate, PaperSearchResult, SearchContext
from paperos.storage.config import StorageConfig
from paperos.storage.objects import LocalFileObjectStore
from paperos.storage.sqlite.repository import SQLitePaperRepository
from paperos.workflows.paper_discovery import PaperDiscoveryWorkflow
from paperos.workflows.search_storage import (
    SearchStorageImportResult,
    SearchStorageImportSummary,
    SearchStorageImportWorkflow,
)


class FakeSearchService:
    def __init__(self, result: PaperSearchResult):
        self.result = result
        self.calls = []

    async def search(
        self,
        raw_query: str,
        *,
        event=None,
        need_fulltext: bool = True,
        context: SearchContext | None = None,
    ) -> PaperSearchResult:
        self.calls.append((raw_query, event, need_fulltext, context))
        return self.result


class FakeImportWorkflow:
    def __init__(self, summary: SearchStorageImportSummary, repository):
        self.summary = summary
        self.repository = repository
        self.calls = []

    async def import_search_result(self, result, **kwargs):
        self.calls.append((result, kwargs))
        return self.summary


class FakeRagResult:
    vector_count = 3
    index_name = "chunk_embeddings"
    profile = "fake:dim3"


class FakeRagIndexService:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    async def index_parser_run(self, parser_run_id: str):
        self.calls.append(parser_run_id)
        if self.fail:
            raise RuntimeError("embedding provider unavailable")
        return FakeRagResult()


class FakeRepository:
    def __init__(self):
        self.done_jobs = []
        self.failed_jobs = []
        self.index_status = []

    async def mark_job_done(self, job_id: str) -> None:
        self.done_jobs.append(job_id)

    async def mark_job_failed_final(self, job_id: str, error_message: str) -> None:
        self.failed_jobs.append((job_id, error_message))

    async def update_index_status(self, **kwargs) -> None:
        self.index_status.append(kwargs)


def test_discover_and_index_searches_imports_and_reports_parse_jobs(tmp_path):
    async def run():
        pdf_path = tmp_path / "searcher" / "fulltext" / "paper.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"%PDF-1.4\n% verified upstream\n")

        candidate = PaperCandidate(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            doi="10.5555/attention",
            source="test",
            fulltext_locations=[
                FulltextLocation(
                    url="https://example.test/attention.pdf",
                    source="test",
                    status=FulltextStatus.VERIFIED_PDF,
                    local_path=str(pdf_path),
                    content_type="application/pdf",
                    sha256="a" * 64,
                    size_bytes=pdf_path.stat().st_size,
                    page_count=15,
                )
            ],
        )
        search_result = PaperSearchResult(
            status="selected",
            candidates=[candidate],
            selected=[candidate],
        )

        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()
        store = LocalFileObjectStore(tmp_path / "objects", tmp_path / "tmp")

        search = FakeSearchService(search_result)
        workflow = PaperDiscoveryWorkflow(
            search_service=search,
            search_storage=SearchStorageImportWorkflow(repository=repo, object_store=store),
        )

        search_context = SearchContext(known_titles=["Attention Is All You Need"])
        result = await workflow.discover_and_index(
            "attention",
            need_fulltext=True,
            process_document=False,
            search_context=search_context,
        )

        assert search.calls == [("attention", None, True, search_context)]
        assert result.imported_count == 1
        assert result.pdf_count == 1
        assert len(result.storage_parse_job_ids) == 1
        assert result.rag_job_ids == []

        job = repo.conn.execute(
            "SELECT job_type FROM paper_jobs WHERE id = ?",
            (result.storage_parse_job_ids[0],),
        ).fetchone()
        assert job["job_type"] == "storage_parse_pdf"

        await repo.aclose()

    asyncio.run(run())


def test_discover_and_index_runs_rag_indexing_for_parser_runs():
    async def run():
        candidate = PaperCandidate(title="Indexed Paper", source="test")
        search_result = PaperSearchResult(
            status="selected",
            candidates=[candidate],
            selected=[candidate],
        )
        summary = SearchStorageImportSummary(
            [
                SearchStorageImportResult(
                    paper_id="p_1",
                    title="Indexed Paper",
                    source="test",
                    job_id="job_parse",
                    rag_job_id="job_rag",
                    parser_run_id="parser_1",
                    imported_pdf=True,
                    metadata_only=False,
                )
            ]
        )
        repo = FakeRepository()
        rag = FakeRagIndexService()
        workflow = PaperDiscoveryWorkflow(
            search_service=FakeSearchService(search_result),
            search_storage=FakeImportWorkflow(summary, repo),
            rag_index_service=rag,
        )

        result = await workflow.discover_and_index("indexed paper")

        assert rag.calls == ["parser_1"]
        assert repo.done_jobs == ["job_rag"]
        assert result.rag_job_ids == ["job_rag"]
        assert result.rag_index_failed_count == 0
        assert result.rag_indexed_vector_count == 3

    asyncio.run(run())


def test_discover_and_index_keeps_import_when_rag_indexing_fails():
    async def run():
        candidate = PaperCandidate(title="Indexed Paper", source="test")
        search_result = PaperSearchResult(
            status="selected",
            candidates=[candidate],
            selected=[candidate],
        )
        summary = SearchStorageImportSummary(
            [
                SearchStorageImportResult(
                    paper_id="p_1",
                    title="Indexed Paper",
                    source="test",
                    job_id="job_parse",
                    rag_job_id="job_rag",
                    parser_run_id="parser_1",
                    imported_pdf=True,
                    metadata_only=False,
                )
            ]
        )
        repo = FakeRepository()
        workflow = PaperDiscoveryWorkflow(
            search_service=FakeSearchService(search_result),
            search_storage=FakeImportWorkflow(summary, repo),
            rag_index_service=FakeRagIndexService(fail=True),
        )

        result = await workflow.discover_and_index("indexed paper")

        assert result.imported_count == 1
        assert result.pdf_count == 1
        assert result.rag_index_failed_count == 1
        assert repo.failed_jobs == [("job_rag", "embedding provider unavailable")]
        assert repo.index_status == [
            {
                "paper_id": "p_1",
                "index_name": "chunk_embeddings",
                "status": "failed",
                "profile": None,
                "message": "embedding provider unavailable",
            }
        ]

    asyncio.run(run())
