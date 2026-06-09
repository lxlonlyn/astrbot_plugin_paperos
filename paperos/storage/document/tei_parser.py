from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from .grobid_models import DocumentAsset, DocumentBlock, DocumentReference, DocumentSection, NormalizedDocument

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


class TEIParser:
    """Best-effort TEI parser for the first storage document-processing pass."""

    def parse(self, tei_xml: str) -> NormalizedDocument:
        root = ET.fromstring(tei_xml)
        title = self._first_text(root, ".//tei:titleStmt/tei:title")
        abstract = self._joined_text(root, ".//tei:profileDesc/tei:abstract")
        sections: list[DocumentSection] = []
        blocks: list[DocumentBlock] = []
        assets: list[DocumentAsset] = []

        if abstract:
            blocks.append(
                DocumentBlock(
                    block_index=len(blocks),
                    block_type="abstract",
                    text=abstract,
                    content_hash=self._hash(abstract),
                )
            )

        for div in root.findall(".//tei:text/tei:body/tei:div", TEI_NS):
            head = self._clean(" ".join(div.findtext("tei:head", default="", namespaces=TEI_NS).split()))
            section_index = None
            if head:
                section_index = len(sections)
                sections.append(
                    DocumentSection(
                        title=head,
                        level=self._section_level(div),
                        order_index=section_index,
                    )
                )
            self._parse_div_children(
                div,
                section_index=section_index,
                parent_section_index=section_index,
                sections=sections,
                blocks=blocks,
                assets=assets,
            )

        references = self._references(root)
        return NormalizedDocument(
            title=title,
            abstract=abstract,
            sections=sections,
            blocks=blocks,
            assets=assets,
            references=references,
            metadata={"source": "tei"},
        )

    def _parse_div_children(
        self,
        div: ET.Element,
        *,
        section_index: int | None,
        parent_section_index: int | None,
        sections: list[DocumentSection],
        blocks: list[DocumentBlock],
        assets: list[DocumentAsset],
    ) -> None:
        for child in list(div):
            tag = self._local_name(child.tag)
            if tag == "head":
                continue
            if tag == "p":
                self._append_text_block(
                    blocks,
                    block_type="paragraph",
                    element=child,
                    section_index=section_index,
                )
            elif tag == "list":
                for item in child.findall("tei:item", TEI_NS):
                    self._append_text_block(
                        blocks,
                        block_type="list_item",
                        element=item,
                        section_index=section_index,
                    )
            elif tag == "figure":
                self._append_figure_or_table(child, section_index=section_index, blocks=blocks, assets=assets)
            elif tag == "table":
                self._append_table(child, section_index=section_index, blocks=blocks, assets=assets)
            elif tag == "formula":
                self._append_formula(child, section_index=section_index, blocks=blocks, assets=assets)
            elif tag == "div":
                child_section_index = self._section_from_div(
                    child,
                    sections=sections,
                    parent_section_index=parent_section_index,
                )
                self._parse_div_children(
                    child,
                    section_index=child_section_index if child_section_index is not None else section_index,
                    parent_section_index=child_section_index if child_section_index is not None else parent_section_index,
                    sections=sections,
                    blocks=blocks,
                    assets=assets,
                )

    def _section_from_div(
        self,
        div: ET.Element,
        *,
        sections: list[DocumentSection],
        parent_section_index: int | None,
    ) -> int | None:
        head = self._clean(" ".join(div.findtext("tei:head", default="", namespaces=TEI_NS).split()))
        if not head:
            return None
        section_index = len(sections)
        level = sections[parent_section_index].level + 1 if parent_section_index is not None else self._section_level(div)
        sections.append(
            DocumentSection(
                title=head,
                level=level,
                order_index=section_index,
                parent_index=parent_section_index,
            )
        )
        return section_index

    def _append_text_block(
        self,
        blocks: list[DocumentBlock],
        *,
        block_type: str,
        element: ET.Element,
        section_index: int | None,
    ) -> int | None:
        text = self._element_text(element)
        if not text:
            return None
        block_index = len(blocks)
        blocks.append(
            DocumentBlock(
                block_index=block_index,
                block_type=block_type,
                text=text,
                section_index=section_index,
                content_hash=self._hash(text),
            )
        )
        return block_index

    def _append_figure_or_table(
        self,
        element: ET.Element,
        *,
        section_index: int | None,
        blocks: list[DocumentBlock],
        assets: list[DocumentAsset],
    ) -> None:
        asset_type = "table" if (element.attrib.get("type") or "").lower() == "table" else "figure"
        label = self._label(element)
        caption = self._caption(element)
        block_type = "table_caption" if asset_type == "table" else "figure_caption"
        linked_block_index = self._append_caption_block(
            blocks,
            block_type=block_type,
            text=caption,
            section_index=section_index,
        )
        assets.append(
            DocumentAsset(
                asset_type=asset_type,
                label=label,
                caption=caption,
                linked_block_index=linked_block_index,
                metadata={"tei_tag": "figure", "tei_type": element.attrib.get("type")},
            )
        )

    def _append_table(
        self,
        element: ET.Element,
        *,
        section_index: int | None,
        blocks: list[DocumentBlock],
        assets: list[DocumentAsset],
    ) -> None:
        label = self._label(element)
        caption = self._caption(element)
        table_text = self._element_text(element)
        text = caption or table_text
        linked_block_index = self._append_caption_block(
            blocks,
            block_type="table_caption",
            text=text,
            section_index=section_index,
        )
        assets.append(
            DocumentAsset(
                asset_type="table",
                label=label,
                caption=caption or table_text,
                linked_block_index=linked_block_index,
                metadata={"tei_tag": "table"},
            )
        )

    def _append_formula(
        self,
        element: ET.Element,
        *,
        section_index: int | None,
        blocks: list[DocumentBlock],
        assets: list[DocumentAsset],
    ) -> None:
        text = self._element_text(element)
        label = self._label(element)
        linked_block_index = self._append_caption_block(
            blocks,
            block_type="formula",
            text=text,
            section_index=section_index,
        )
        assets.append(
            DocumentAsset(
                asset_type="formula",
                label=label,
                caption=text,
                linked_block_index=linked_block_index,
                metadata={"tei_tag": "formula"},
            )
        )

    def _append_caption_block(
        self,
        blocks: list[DocumentBlock],
        *,
        block_type: str,
        text: str | None,
        section_index: int | None,
    ) -> int | None:
        text = self._clean(text or "")
        if not text:
            return None
        block_index = len(blocks)
        blocks.append(
            DocumentBlock(
                block_index=block_index,
                block_type=block_type,
                text=text,
                section_index=section_index,
                content_hash=self._hash(text),
            )
        )
        return block_index

    def _references(self, root: ET.Element) -> list[DocumentReference]:
        out: list[DocumentReference] = []
        for idx, item in enumerate(root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)):
            raw_text = self._clean(" ".join("".join(item.itertext()).split()))
            if not raw_text:
                continue
            title = self._first_text(item, ".//tei:title")
            year = self._extract_year(self._first_attr(item, ".//tei:date", "when"))
            doi = None
            for idno in item.findall(".//tei:idno", TEI_NS):
                if (idno.attrib.get("type") or "").lower() == "doi":
                    doi = self._clean(idno.text or "")
            out.append(
                DocumentReference(
                    ref_key=item.attrib.get("{http://www.w3.org/XML/1998/namespace}id") or f"ref-{idx}",
                    raw_text=raw_text,
                    title=title,
                    year=year,
                    doi=doi or None,
                )
            )
        return out

    def _first_text(self, root: ET.Element, path: str) -> str | None:
        found = root.find(path, TEI_NS)
        if found is None:
            return None
        text = self._clean(" ".join("".join(found.itertext()).split()))
        return text or None

    def _joined_text(self, root: ET.Element, path: str) -> str | None:
        found = root.find(path, TEI_NS)
        if found is None:
            return None
        text = self._clean(" ".join("".join(found.itertext()).split()))
        return text or None

    def _first_attr(self, root: ET.Element, path: str, attr: str) -> str | None:
        found = root.find(path, TEI_NS)
        return found.attrib.get(attr) if found is not None else None

    def _element_text(self, element: ET.Element) -> str:
        return self._clean(" ".join("".join(element.itertext()).split()))

    def _label(self, element: ET.Element) -> str | None:
        label = self._clean(element.findtext("tei:label", default="", namespaces=TEI_NS))
        return label or element.attrib.get("{http://www.w3.org/XML/1998/namespace}id")

    def _caption(self, element: ET.Element) -> str | None:
        for path in ("tei:figDesc", "tei:head", "tei:caption"):
            found = element.find(path, TEI_NS)
            if found is not None:
                text = self._element_text(found)
                if text:
                    return text
        return None

    def _local_name(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def _section_level(self, div: ET.Element) -> int:
        depth = 0
        parent = div
        while parent.tag.endswith("div"):
            depth += 1
            break
        return max(1, depth)

    def _extract_year(self, value: str | None) -> int | None:
        match = re.search(r"(19|20)\d{2}", value or "")
        return int(match.group(0)) if match else None

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
