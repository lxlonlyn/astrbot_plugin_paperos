from __future__ import annotations

from pathlib import Path

import httpx


class GrobidClient:
    """Minimal GROBID REST client for local document processing."""

    def __init__(self, *, base_url: str = "http://localhost:8070", timeout_seconds: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def process_fulltext_document(self, pdf_path: Path) -> str:
        with Path(pdf_path).open("rb") as pdf:
            response = await self._client.post(
                f"{self.base_url}/api/processFulltextDocument",
                files={"input": (Path(pdf_path).name, pdf, "application/pdf")},
            )
        response.raise_for_status()
        return response.text

    async def aclose(self) -> None:
        await self._client.aclose()
