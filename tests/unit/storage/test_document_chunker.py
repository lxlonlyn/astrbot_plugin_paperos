from __future__ import annotations

from paperos.storage.document.chunker import DocumentChunker
from paperos.storage.document.grobid_models import DocumentBlock, DocumentSection, NormalizedDocument


def _text(prefix: str, words: int = 90) -> str:
    return prefix + " " + " ".join(f"word{i}" for i in range(words)) + "."


def test_chunker_merges_consecutive_paragraphs_by_section():
    document = NormalizedDocument(
        title="Chunking Paper",
        sections=[DocumentSection(title="Introduction"), DocumentSection(title="Method")],
        blocks=[
            DocumentBlock(block_index=0, block_type="paragraph", text=_text("First"), section_index=0),
            DocumentBlock(block_index=1, block_type="paragraph", text=_text("Second"), section_index=0),
            DocumentBlock(block_index=2, block_type="paragraph", text=_text("Third"), section_index=1),
        ],
    )

    chunks = DocumentChunker(min_chars=120, target_chars=1000, max_chars=1400).chunks(document)

    assert len(chunks) == 2
    assert chunks[0]["section_title"] == "Introduction"
    assert chunks[0]["source_block_ids"] == [0, 1]
    assert "First" in chunks[0]["text"]
    assert "Second" in chunks[0]["text"]
    assert chunks[0]["metadata"]["chunk_policy"] == "section_merge_v1"
    assert chunks[1]["section_title"] == "Method"
    assert chunks[1]["source_block_ids"] == [2]


def test_chunker_filters_noise_and_short_blocks():
    document = NormalizedDocument(
        title="Noise Paper",
        sections=[DocumentSection(title="Results")],
        blocks=[
            DocumentBlock(block_index=0, block_type="paragraph", text="tiny", section_index=0),
            DocumentBlock(block_index=1, block_type="paragraph", text="Figure 1. Overview of the system.", section_index=0),
            DocumentBlock(block_index=2, block_type="figure_caption", text=_text("Caption"), section_index=0),
            DocumentBlock(block_index=3, block_type="paragraph", text=_text("Useful", 120), section_index=0),
        ],
    )

    chunks = DocumentChunker(min_chars=120, target_chars=1000, max_chars=1400).chunks(document)

    assert len(chunks) == 1
    assert chunks[0]["source_block_ids"] == [3]
    assert "Useful" in chunks[0]["text"]
    assert "Figure 1" not in chunks[0]["text"]


def test_chunker_splits_long_paragraph_and_merges_short_tail():
    sentence = "This sentence carries enough scientific context for chunking."
    long_text = " ".join(sentence for _ in range(80))
    short_tail = _text("Tail", 20)
    document = NormalizedDocument(
        title="Long Paper",
        sections=[DocumentSection(title="Discussion")],
        blocks=[
            DocumentBlock(block_index=0, block_type="paragraph", text=long_text, section_index=0),
            DocumentBlock(block_index=1, block_type="paragraph", text=short_tail, section_index=0),
        ],
    )

    chunks = DocumentChunker(min_chars=250, target_chars=700, max_chars=900).chunks(document)

    assert len(chunks) > 1
    assert chunks[-1]["source_block_ids"][-1] == 1
    assert len(chunks[-1]["text"]) >= 250
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
