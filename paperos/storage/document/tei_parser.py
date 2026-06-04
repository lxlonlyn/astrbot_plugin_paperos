from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from .grobid_models import DocumentBlock, DocumentReference, DocumentSection, NormalizedDocument

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


class TEIParser:
    """Best-effort TEI parser for the first storage document-processing pass."""

    def parse(self, tei_xml: str) -> NormalizedDocument:
        root = ET.fromstring(tei_xml)
        title = self._first_text(root, ".//tei:titleStmt/tei:title")
        abstract = self._joined_text(root, ".//tei:profileDesc/tei:abstract")
        sections: list[DocumentSection] = []
        blocks: list[DocumentBlock] = []

        for div in root.findall(".//tei:text/tei:body//tei:div", TEI_NS):
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
            for para in div.findall("tei:p", TEI_NS):
                text = self._clean(" ".join("".join(para.itertext()).split()))
                if not text:
                    continue
                blocks.append(
                    DocumentBlock(
                        block_index=len(blocks),
                        block_type="paragraph",
                        text=text,
                        section_index=section_index,
                        content_hash=self._hash(text),
                    )
                )

        references = self._references(root)
        return NormalizedDocument(
            title=title,
            abstract=abstract,
            sections=sections,
            blocks=blocks,
            references=references,
            metadata={"source": "tei"},
        )

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
