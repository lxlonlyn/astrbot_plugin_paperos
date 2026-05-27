from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

from .url_tools import canonical_url, strip_html


@dataclass
class ExtractedHTML:
    title: str = ""
    meta: dict[str, list[str]] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)

    def first_meta(self, *names: str) -> str | None:
        for name in names:
            values = self.meta.get(name.lower())
            if values:
                return values[0]
        return None

    def all_meta(self, *names: str) -> list[str]:
        out: list[str] = []
        for name in names:
            out.extend(self.meta.get(name.lower(), []))
        return out


class PaperHTMLParser(HTMLParser):
    """Small dependency-free extractor for paper landing pages.

    We intentionally avoid BeautifulSoup here to keep AstrBot plugin dependency
    management simple. The parser only needs citation meta tags and href links.
    """

    def __init__(self, *, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.data = ExtractedHTML()
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").strip().lower()
            content = (attrs_dict.get("content") or "").strip()
            if key and content:
                self.data.meta.setdefault(key, []).append(strip_html(content))
            return
        if tag in {"a", "link"}:
            href = attrs_dict.get("href")
            if href:
                self.data.links.append(canonical_url(href, base_url=self.base_url))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self._title_parts.append(data.strip())

    def close(self) -> None:
        super().close()
        if self._title_parts and not self.data.title:
            self.data.title = strip_html(" ".join(self._title_parts))


def parse_paper_html(html: str, *, base_url: str) -> ExtractedHTML:
    parser = PaperHTMLParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return parser.data
