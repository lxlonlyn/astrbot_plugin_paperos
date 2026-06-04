from __future__ import annotations

import asyncio

from paperos.search.models import FulltextLocation, FulltextStatus, PaperCandidate, PaperSearchResult, SearchContext
from paperos.storage.config import StorageConfig
from paperos.storage.objects import LocalFileObjectStore
from paperos.storage.sqlite.repository import SQLitePaperRepository
from paperos.workflows.paper_discovery import PaperDiscoveryWorkflow
from paperos.workflows.search_storage import SearchStorageImportWorkflow


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
