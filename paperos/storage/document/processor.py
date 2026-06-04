from __future__ import annotations

from pathlib import Path

from .chunker import DocumentChunker
from .grobid_client import GrobidClient
from .grobid_models import NormalizedDocument
from .normalizer import DocumentNormalizer
from .tei_parser import TEIParser


class DocumentProcessor:
    """Compose local PDF document processing components.

    This first pass exposes the processing shape without owning job execution.
    Future storage workers can persist parser_runs, TEI objects, normalized
    document objects, SQL rows, chunks, and FTS through repository APIs.
    """

    def __init__(
        self,
        *,
        grobid_client: GrobidClient | None = None,
        tei_parser: TEIParser | None = None,
        normalizer: DocumentNormalizer | None = None,
        chunker: DocumentChunker | None = None,
    ):
        self.grobid_client = grobid_client or GrobidClient()
        self.tei_parser = tei_parser or TEIParser()
        self.normalizer = normalizer or DocumentNormalizer()
        self.chunker = chunker or DocumentChunker()

    async def process_pdf(self, pdf_path: Path) -> tuple[str, NormalizedDocument, dict, list[dict]]:
        tei_xml = await self.grobid_client.process_fulltext_document(pdf_path)
        document = self.tei_parser.parse(tei_xml)
        normalized = self.normalizer.to_jsonable(document)
        chunks = self.chunker.chunks(document)
        return tei_xml, document, normalized, chunks

    async def aclose(self) -> None:
        await self.grobid_client.aclose()
