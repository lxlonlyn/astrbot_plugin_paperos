from __future__ import annotations

import asyncio

from paperos.storage.config import StorageConfig
from paperos.storage.document.chunker import DocumentChunker
from paperos.storage.document.tei_parser import TEIParser
from paperos.storage.models import PaperRecordDraft
from paperos.storage.sqlite.repository import SQLitePaperRepository


TEI_SAMPLE = """\
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt><title>Structured Paper</title></titleStmt>
    </fileDesc>
    <profileDesc>
      <abstract>
        <p>This abstract contains enough main scientific context to become a retrievable text block for the paper.</p>
      </abstract>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div>
        <head>Introduction</head>
        <p>This paragraph explains the motivation and provides enough content for the main text block extraction path.</p>
        <list>
          <item>This list item is also part of the main scientific text and should be available to the chunker.</item>
        </list>
        <figure xml:id="fig_1">
          <label>Figure 1</label>
          <figDesc>System architecture diagram with retrieval and storage components.</figDesc>
        </figure>
        <figure type="table" xml:id="tab_1">
          <label>Table 1</label>
          <figDesc>Dataset statistics grouped by task and evaluation split.</figDesc>
        </figure>
        <formula xml:id="formula_1">E = mc^2</formula>
        <div>
          <head>Background</head>
          <p>This nested paragraph should belong to a child section instead of being parsed twice.</p>
        </div>
      </div>
    </body>
  </text>
</TEI>
"""


def test_tei_parser_separates_sections_main_text_and_assets():
    document = TEIParser().parse(TEI_SAMPLE)

    assert document.title == "Structured Paper"
    assert [section.title for section in document.sections] == ["Introduction", "Background"]
    assert document.sections[1].parent_index == 0
    block_types = [block.block_type for block in document.blocks]
    assert block_types == [
        "abstract",
        "paragraph",
        "list_item",
        "figure_caption",
        "table_caption",
        "formula",
        "paragraph",
    ]
    assert all(block.text != "Introduction" for block in document.blocks)
    assert [asset.asset_type for asset in document.assets] == ["figure", "table", "formula"]
    assert document.assets[0].label == "Figure 1"
    assert document.assets[0].caption == "System architecture diagram with retrieval and storage components."
    assert document.assets[0].linked_block_index == 3

    chunks = DocumentChunker(min_chars=80, target_chars=500, max_chars=900).chunks(document)
    chunk_text = "\n".join(chunk["text"] for chunk in chunks)
    assert "motivation" in chunk_text
    assert "list item" in chunk_text
    assert "System architecture diagram" not in chunk_text
    assert "Dataset statistics" not in chunk_text
    assert "E = mc^2" not in chunk_text


def test_repository_persists_extracted_assets(tmp_path):
    async def run():
        repo = SQLitePaperRepository(tmp_path / "paperos.sqlite3", StorageConfig())
        await repo.initialize()
        paper_id = await repo.upsert_paper(
            PaperRecordDraft(title="Structured Paper", source="test"),
            source_query="structured",
        )
        version_id = await repo.current_version_id(paper_id)
        document = TEIParser().parse(TEI_SAMPLE)
        chunks = DocumentChunker(min_chars=80, target_chars=500, max_chars=900).chunks(document)

        parser_run_id = await repo.persist_document_processing_result(
            paper_id=paper_id,
            version_id=version_id,
            object_id=None,
            parser_name="grobid",
            parser_version="test",
            raw_output_object_id=None,
            normalized_object_id=None,
            document=document,
            chunks=chunks,
        )

        assets = repo.conn.execute(
            """
            SELECT a.asset_type, a.label, a.caption, b.block_type
            FROM extracted_assets a
            LEFT JOIN document_blocks b ON b.id = a.linked_block_id
            WHERE a.parser_run_id = ?
            ORDER BY a.asset_type
            """,
            (parser_run_id,),
        ).fetchall()
        assert [(row["asset_type"], row["block_type"]) for row in assets] == [
            ("figure", "figure_caption"),
            ("formula", "formula"),
            ("table", "table_caption"),
        ]
        assert any(row["label"] == "Figure 1" for row in assets)
        await repo.aclose()

    asyncio.run(run())
