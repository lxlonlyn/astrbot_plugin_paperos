from __future__ import annotations

from .models import EvidencePack, RetrievedChunk


class RagPresenter:
    def format_evidence_pack(self, pack: EvidencePack, *, max_items: int = 5) -> str:
        lines = [f"PaperOS RAG Evidence\nquery: {pack.query}"]
        if pack.is_empty:
            lines.append("没有在本地 chunks 中检索到证据。")
            return "\n".join(lines)

        lines.append(f"evidence_chunks: {len(pack.items)}")
        for idx, item in enumerate(pack.items[:max_items], start=1):
            chunk = item.chunk
            lines.extend(
                [
                    "",
                    f"{idx}. {chunk.title}",
                    f"   chunk_id={chunk.chunk_id}; paper_id={chunk.paper_id}; score={chunk.score:.4f}",
                    f"   section={chunk.section_path or chunk.section_title or '-'}; pages={self._pages(chunk)}",
                    f"   text={self._short(chunk.text, 420)}",
                ]
            )
            if item.neighbors:
                neighbor_ids = ", ".join(neighbor.chunk_id for neighbor in item.neighbors[:3])
                lines.append(f"   neighbors={neighbor_ids}")
        if len(pack.items) > max_items:
            lines.append(f"\n... 还有 {len(pack.items) - max_items} 个 evidence chunk")
        return "\n".join(lines)

    def _pages(self, chunk: RetrievedChunk) -> str:
        if chunk.page_start is None and chunk.page_end is None:
            return "-"
        if chunk.page_start == chunk.page_end or chunk.page_end is None:
            return str(chunk.page_start)
        return f"{chunk.page_start}-{chunk.page_end}"

    def _short(self, text: str, limit: int) -> str:
        text = " ".join((text or "").split())
        return text if len(text) <= limit else text[: limit - 3] + "..."
