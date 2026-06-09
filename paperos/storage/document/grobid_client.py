from __future__ import annotations

from pathlib import Path

import httpx

DEFAULT_FULLTEXT_OPTIONS = [
    ("generateIDs", "1"),
    ("segmentSentences", "1"),
    ("includeRawCitations", "1"),
    ("teiCoordinates", "p"),
    ("teiCoordinates", "head"),
    ("teiCoordinates", "figure"),
    ("teiCoordinates", "formula"),
    ("teiCoordinates", "biblStruct"),
]
DEFAULT_FULLTEXT_FORM_DATA = {
    "generateIDs": "1",
    "segmentSentences": "1",
    "includeRawCitations": "1",
    "teiCoordinates": ["p", "head", "figure", "formula", "biblStruct"],
}


class GrobidServiceError(RuntimeError):
    pass


class GrobidClient:
    """Minimal GROBID REST client for local document processing."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8070",
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = (base_url or "http://localhost:8070").rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)

    async def process_fulltext_document(self, pdf_path: Path) -> str:
        endpoint = f"{self.base_url}/api/processFulltextDocument"
        try:
            path = Path(pdf_path)
            pdf_bytes = path.read_bytes()
            response = await self._client.post(
                endpoint,
                files={"input": (path.name, pdf_bytes, "application/pdf")},
                data=DEFAULT_FULLTEXT_FORM_DATA,
            )
            response.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise GrobidServiceError(
                f"无法连接 GROBID 服务：{self.base_url}。请确认 storage.grobid_base_url 配置正确，"
                "并且 GROBID 服务已启动。"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise GrobidServiceError(
                f"GROBID 服务处理超时：{self.base_url}。请调大 storage.grobid_timeout_seconds，"
                "或检查 GROBID 服务状态。"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise GrobidServiceError(
                f"GROBID 服务返回 HTTP {exc.response.status_code}：{endpoint}"
            ) from exc
        except httpx.HTTPError as exc:
            raise GrobidServiceError(f"GROBID 请求失败：{endpoint}，错误：{exc}") from exc
        return response.text

    async def aclose(self) -> None:
        await self._client.aclose()
