from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..storage.config import StorageConfig
from ..storage.document import DocumentProcessor
from ..storage.document.tei_header import parse_tei_header_metadata


@dataclass(frozen=True)
class UploadProbeResult:
    source_path: str
    title: str | None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    sections_count: int = 0
    blocks_count: int = 0
    references_count: int = 0
    chunks_count: int = 0
    message: str = "GROBID 解析完成"


class UploadProbeWorkflow:
    """Probe AstrBot file upload and configured storage document processing."""

    def __init__(self, *, storage_cfg: StorageConfig):
        self.storage_cfg = storage_cfg

    async def run(self, pdf_path: Path) -> UploadProbeResult:
        processor = DocumentProcessor(storage_cfg=self.storage_cfg)
        try:
            tei_xml, document, _normalized, chunks = await processor.process_pdf(pdf_path)
        finally:
            await processor.aclose()

        header = parse_tei_header_metadata(tei_xml)
        return UploadProbeResult(
            source_path=str(pdf_path),
            title=document.title,
            authors=header.authors,
            year=header.year,
            venue=header.venue,
            doi=header.doi,
            abstract=document.abstract,
            sections_count=len(document.sections),
            blocks_count=len(document.blocks),
            references_count=len(document.references),
            chunks_count=len(chunks),
        )


def format_upload_probe_result(result: UploadProbeResult) -> str:
    return "\n".join(
        [
            f"PaperOS Upload Probe: {result.message}",
            "",
            "文件：",
            f"- path: {result.source_path}",
            "- mode: tmp upload probe",
            "",
            "元信息：",
            f"- Title: {_value(result.title)}",
            f"- Authors: {_authors(result.authors)}",
            f"- Year: {_value(result.year)}",
            f"- Venue: {_value(result.venue)}",
            f"- DOI: {_value(result.doi)}",
            f"- Abstract: {_value(result.abstract)}",
            "",
            "解析统计：",
            f"- Sections: {result.sections_count}",
            f"- Blocks: {result.blocks_count}",
            f"- References: {result.references_count}",
            f"- Chunks: {result.chunks_count}",
            "",
            "边界：",
            "- 已调用：storage DocumentProcessor / configured GrobidClient",
            "- 未调用：LLM / search / crawler / API / importer / SQLite / RAG",
        ]
    )


def _value(value: object | None) -> str:
    if value is None:
        return "未解析到"
    text = str(value).strip()
    return text if text else "未解析到"


def _authors(authors: list[str]) -> str:
    return ", ".join(authors) if authors else "未解析到"
