from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .grobid_models import DocumentBlock, NormalizedDocument


@dataclass(frozen=True)
class _ChunkUnit:
    text: str
    block: DocumentBlock


class DocumentChunker:
    def __init__(
        self,
        *,
        min_chars: int = 500,
        target_chars: int = 1800,
        max_chars: int = 2600,
        overlap_chars: int = 200,
    ):
        self.min_chars = min_chars
        self.target_chars = target_chars
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunks(self, document: NormalizedDocument, *, paper_title: str | None = None) -> list[dict]:
        chunks: list[dict] = []
        section_titles = {idx: section.title for idx, section in enumerate(document.sections)}
        buffer: list[_ChunkUnit] = []
        buffer_text_len = 0
        current_section_index: int | None = None

        def flush(*, force: bool = False) -> None:
            nonlocal buffer, buffer_text_len
            if not buffer:
                return
            if not force and buffer_text_len < self.min_chars:
                return
            text = "\n\n".join(unit.text for unit in buffer).strip()
            if not text:
                buffer = []
                buffer_text_len = 0
                return
            first = buffer[0].block
            last = buffer[-1].block
            section_title = section_titles.get(first.section_index) if first.section_index is not None else None
            block_ids = _unique_block_ids(unit.block.block_index for unit in buffer)
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "chunk_type": "paragraph",
                    "section_title": section_title,
                    "section_path": section_title,
                    "text": text,
                    "embedding_text": self._embedding_text(
                        paper_title=paper_title or document.title,
                        section_title=section_title,
                        chunk_type="paragraph",
                        text=text,
                    ),
                    "content_hash": _content_hash(text),
                    "source_block_ids": block_ids,
                    "page_start": first.page_start,
                    "page_end": last.page_end,
                    "token_count": len(text.split()),
                    "metadata": {
                        "source_block_count": len(block_ids),
                        "chunk_policy": "section_merge_v1",
                    },
                }
            )
            buffer = []
            buffer_text_len = 0

        for block in document.blocks:
            text = (block.text or "").strip()
            if not text:
                continue
            if not self._is_main_text_block(block.block_type, text):
                continue

            if current_section_index is None:
                current_section_index = block.section_index
            if block.section_index != current_section_index:
                flush(force=True)
                current_section_index = block.section_index

            for part in self._split_long_text(text):
                if buffer_text_len and buffer_text_len + len(part) > self.max_chars:
                    flush(force=True)
                buffer.append(_ChunkUnit(text=part, block=block))
                buffer_text_len += len(part)
                if buffer_text_len >= self.target_chars:
                    flush(force=True)

        flush(force=True)
        chunks = self._merge_too_short_tail_chunks(
            chunks,
            paper_title=paper_title or document.title,
        )
        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
        return chunks

    def _is_main_text_block(self, block_type: str, text: str) -> bool:
        if block_type not in {"paragraph", "abstract", "list_item"}:
            return False
        if len(text) < 40:
            return False
        if self._looks_like_noise(text):
            return False
        return True

    def _looks_like_noise(self, text: str) -> bool:
        lower = text.lower().strip()
        if lower.startswith(("figure ", "fig. ", "table ")):
            return True
        if len(text.split()) <= 6 and not text.endswith("."):
            return True
        return False

    def _split_long_text(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]

        parts: list[str] = []
        buffer: list[str] = []
        buffer_len = 0
        for sentence in _split_sentences(text):
            if not sentence:
                continue
            if len(sentence) > self.max_chars:
                if buffer:
                    parts.append(" ".join(buffer).strip())
                    buffer = []
                    buffer_len = 0
                parts.extend(_split_by_chars(sentence, self.max_chars, self.overlap_chars))
                continue
            if buffer_len and buffer_len + len(sentence) > self.max_chars:
                parts.append(" ".join(buffer).strip())
                buffer = []
                buffer_len = 0
            buffer.append(sentence)
            buffer_len += len(sentence)
            if buffer_len >= self.target_chars:
                parts.append(" ".join(buffer).strip())
                buffer = []
                buffer_len = 0
        if buffer:
            parts.append(" ".join(buffer).strip())
        return [part for part in parts if part]

    def _merge_too_short_tail_chunks(
        self,
        chunks: list[dict],
        *,
        paper_title: str | None,
    ) -> list[dict]:
        if len(chunks) <= 1:
            return chunks

        merged: list[dict] = []
        i = 0
        while i < len(chunks):
            chunk = chunks[i]
            if len(str(chunk.get("text") or "")) < self.min_chars:
                if merged:
                    merged[-1] = self._merge_chunks(
                        merged[-1],
                        chunk,
                        paper_title=paper_title,
                    )
                elif i + 1 < len(chunks):
                    merged.append(
                        self._merge_chunks(
                            chunk,
                            chunks[i + 1],
                            paper_title=paper_title,
                        )
                    )
                    i += 1
                else:
                    merged.append(chunk)
            else:
                merged.append(chunk)
            i += 1
        return merged

    def _merge_chunks(self, left: dict, right: dict, *, paper_title: str | None) -> dict:
        text = "\n\n".join(
            part.strip()
            for part in (str(left.get("text") or ""), str(right.get("text") or ""))
            if part.strip()
        )
        section_title = left.get("section_title")
        if section_title != right.get("section_title"):
            section_title = left.get("section_title") or right.get("section_title")
        source_block_ids = _unique_block_ids(
            [
                *(left.get("source_block_ids") or []),
                *(right.get("source_block_ids") or []),
            ]
        )
        metadata = {
            **(left.get("metadata") or {}),
            "source_block_count": len(source_block_ids),
            "chunk_policy": "section_merge_v1",
            "merged_short_chunk": True,
        }
        return {
            **left,
            "chunk_type": "paragraph",
            "section_title": section_title,
            "section_path": section_title,
            "text": text,
            "embedding_text": self._embedding_text(
                paper_title=paper_title,
                section_title=section_title,
                chunk_type="paragraph",
                text=text,
            ),
            "content_hash": _content_hash(text),
            "source_block_ids": source_block_ids,
            "page_start": left.get("page_start"),
            "page_end": right.get("page_end") or left.get("page_end"),
            "token_count": len(text.split()),
            "metadata": metadata,
        }

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


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]


def _split_by_chars(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    parts: list[str] = []
    start = 0
    step_back = max(0, min(overlap_chars, max_chars // 3))
    while start < len(text):
        end = min(len(text), start + max_chars)
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - step_back, start + 1)
    return [part for part in parts if part]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unique_block_ids(values) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
