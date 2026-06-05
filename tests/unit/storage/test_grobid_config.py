from __future__ import annotations

import asyncio

import httpx

from paperos.storage.config import StorageConfig, load_storage_config
from paperos.storage.document.grobid_client import GrobidClient, GrobidServiceError
from paperos.storage.document.processor import DocumentProcessor


def test_storage_config_loads_grobid_settings():
    cfg = load_storage_config(
        {
            "storage": {
                "grobid_base_url": "http://grobid.internal:8070/",
                "grobid_timeout_seconds": 42,
                "vector_backend": "lancedb",
                "vector_table_name": "paperos_vectors",
            }
        }
    )

    assert cfg.grobid_base_url == "http://grobid.internal:8070"
    assert cfg.grobid_timeout_seconds == 42.0
    assert cfg.vector_backend == "lancedb"
    assert cfg.vector_table_name == "paperos_vectors"


def test_document_processor_uses_storage_grobid_config():
    cfg = StorageConfig(
        grobid_base_url="http://grobid.example:8070",
        grobid_timeout_seconds=12,
    )

    processor = DocumentProcessor(storage_cfg=cfg)
    assert processor.grobid_client.base_url == "http://grobid.example:8070"

    asyncio.run(processor.aclose())


def test_grobid_client_reports_connection_error(tmp_path):
    async def run():
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = GrobidClient(
            base_url="http://grobid.test:8070",
            transport=httpx.MockTransport(handler),
        )
        try:
            try:
                await client.process_fulltext_document(pdf_path)
            except GrobidServiceError as exc:
                message = str(exc)
                assert "无法连接 GROBID 服务" in message
                assert "http://grobid.test:8070" in message
            else:
                raise AssertionError("expected GrobidServiceError")
        finally:
            await client.aclose()

    asyncio.run(run())
