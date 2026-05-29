from __future__ import annotations

import asyncio

from paperos.search.models import FulltextLocation, FulltextStatus, PaperCandidate, PaperSearchResult
from paperos.storage.config import StorageConfig
from paperos.storage.objects import LocalFileObjectStore
from paperos.storage.sqlite.repository import SQLitePaperRepository
from paperos.workflows.search_storage import SearchStorageImportWorkflow


def test_import_search_result_persists_metadata_pdf_and_rag_job(tmp_path):
    async def run():
        pdf_path = tmp_path / "searcher" / "fulltext" / "paper.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"%PDF-1.4\n% fake but already verified by search\n")

        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()
        store = LocalFileObjectStore(tmp_path / "objects", tmp_path / "tmp")
        workflow = SearchStorageImportWorkflow(repository=repo, object_store=store)

        candidate = PaperCandidate(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            year=2017,
            venue="NeurIPS",
            doi="10.5555/attention",
            landing_url="https://example.test/attention",
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

        summary = await workflow.import_search_result(
            PaperSearchResult(status="selected", candidates=[candidate], selected=[candidate]),
            source_query="attention",
            cleanup_temporary_pdf=True,
        )

        assert summary.imported_count == 1
        assert summary.pdf_count == 1
        assert summary.job_count == 1
        assert summary.results[0].object_id
        assert summary.results[0].job_id
        assert summary.results[0].temporary_pdf_removed is True
        assert not pdf_path.exists()
        assert await repo.find_by_identifier(doi="10.5555/attention") is not None

        await repo.aclose()

    asyncio.run(run())
