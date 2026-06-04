from __future__ import annotations

from .grobid_models import NormalizedDocument


class DocumentChunker:
    def __init__(self, *, max_chars: int = 1800):
        self.max_chars = max_chars

    def chunks(self, document: NormalizedDocument, *, paper_title: str | None = None) -> list[dict]:
        chunks: list[dict] = []
        section_titles = {idx: section.title for idx, section in enumerate(document.sections)}
        for block in document.blocks:
            if not block.text:
                continue
            section_title = section_titles.get(block.section_index) if block.section_index is not None else None
            text_parts = [block.text[i : i + self.max_chars] for i in range(0, len(block.text), self.max_chars)]
            for part in text_parts:
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "chunk_type": block.block_type,
                        "section_title": section_title,
                        "section_path": section_title,
                        "text": part,
                        "embedding_text": self._embedding_text(
                            paper_title=paper_title or document.title,
                            section_title=section_title,
                            chunk_type=block.block_type,
                            text=part,
                        ),
                        "content_hash": block.content_hash,
                        "source_block_ids": [block.block_index],
                        "page_start": block.page_start,
                        "page_end": block.page_end,
                    }
                )
        return chunks

    def _embedding_text(
        self,
        *,
        paper_title: str | None,
        section_title: str | None,
        chunk_type: str,
        text: str,
    ) -> str:
        parts = []
        if paper_title:
            parts.append(f"Paper: {paper_title}")
        if section_title:
            parts.append(f"Section: {section_title}")
        parts.append(f"Type: {chunk_type}")
        parts.append("")
        parts.append("Content:")
        parts.append(text)
        return "\n".join(parts)
