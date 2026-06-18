from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


@dataclass(frozen=True)
class TEIHeaderMetadata:
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    venue: str | None = None


def parse_tei_header_metadata(tei_xml: str) -> TEIHeaderMetadata:
    root = ET.fromstring(tei_xml)
    return TEIHeaderMetadata(
        authors=_authors(root),
        year=_year(root),
        doi=_doi(root),
        venue=_venue(root),
    )


def _authors(root: ET.Element) -> list[str]:
    paths = [
        ".//tei:sourceDesc//tei:biblStruct//tei:analytic/tei:author",
        ".//tei:titleStmt/tei:author",
    ]
    names: list[str] = []
    seen: set[str] = set()
    for path in paths:
        for author in root.findall(path, TEI_NS):
            name = _author_name(author)
            key = name.casefold()
            if name and key not in seen:
                names.append(name)
                seen.add(key)
    return names


def _author_name(author: ET.Element) -> str:
    pers_name = author.find(".//tei:persName", TEI_NS)
    node = pers_name if pers_name is not None else author
    parts: list[str] = []
    for tag in ("forename", "surname"):
        for item in node.findall(f".//tei:{tag}", TEI_NS):
            text = _text(item)
            if text:
                parts.append(text)
    if parts:
        return " ".join(parts)
    return _text(node)


def _doi(root: ET.Element) -> str | None:
    for item in root.findall(".//tei:idno", TEI_NS):
        if (item.attrib.get("type") or "").lower() == "doi":
            value = _text(item)
            if value:
                return value
    return None


def _year(root: ET.Element) -> int | None:
    for path in (".//tei:imprint/tei:date", ".//tei:date"):
        for item in root.findall(path, TEI_NS):
            raw = item.attrib.get("when") or _text(item)
            if not raw:
                continue
            match = re.search(r"\b(19|20)\d{2}\b", raw)
            if match:
                return int(match.group(0))
    return None


def _venue(root: ET.Element) -> str | None:
    for path in (".//tei:monogr/tei:title", ".//tei:meeting"):
        for item in root.findall(path, TEI_NS):
            value = _text(item)
            if value:
                return value
    return None


def _text(node: ET.Element) -> str:
    return " ".join(" ".join(node.itertext()).split())
