from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlunparse

_ARXIV_NEW_RE = re.compile(r"(?:arxiv:)?(?P<id>\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_ARXIV_OLD_RE = re.compile(r"(?P<id>(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)", re.I)
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", text or ""))).strip()


def clean_redirect_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "duckduckgo.com" in host and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return url


def canonical_url(url: str, *, base_url: str | None = None) -> str:
    if base_url:
        url = urljoin(base_url, url)
    url = clean_redirect_url(unescape(url.strip()))
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    # Drop fragments; they hurt dedup and do not affect PDF identity.
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def looks_like_http_url(url: str | None) -> bool:
    return bool(url and url.lower().startswith(("http://", "https://")))


def looks_like_pdf_url(url: str | None) -> bool:
    if not url:
        return False
    lower = url.lower()
    parsed = urlparse(lower)
    return parsed.path.endswith(".pdf") or "/pdf/" in parsed.path or parsed.path.endswith("/pdf")


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return [m.group(0).rstrip(".,;)\"]'") for m in re.finditer(r"https?://\S+", text, re.I)]


def extract_doi(text: str | None) -> str | None:
    if not text:
        return None
    match = _DOI_RE.search(text)
    return match.group(1).rstrip(".,;)").lower() if match else None


def extract_arxiv_id(text: str | None) -> str | None:
    if not text:
        return None
    decoded = unquote(text)
    for marker in ("/abs/", "/pdf/"):
        if marker in decoded:
            after = decoded.split(marker, 1)[1]
            after = after.split("?", 1)[0].split("#", 1)[0].strip("/")
            if after.endswith(".pdf"):
                after = after[:-4]
            if after:
                return normalize_arxiv_id(after)
    match = _ARXIV_NEW_RE.search(decoded)
    if match:
        return normalize_arxiv_id(match.group("id"))
    match = _ARXIV_OLD_RE.search(decoded)
    if match:
        return normalize_arxiv_id(match.group("id"))
    return None


def normalize_arxiv_id(arxiv_id: str | None) -> str | None:
    if not arxiv_id:
        return None
    arxiv_id = arxiv_id.strip()
    if arxiv_id.lower().startswith("arxiv:"):
        arxiv_id = arxiv_id.split(":", 1)[1]
    if arxiv_id.endswith(".pdf"):
        arxiv_id = arxiv_id[:-4]
    return arxiv_id or None


def arxiv_abs_url(arxiv_id: str) -> str:
    arxiv_id = normalize_arxiv_id(arxiv_id) or arxiv_id
    return "https://arxiv.org/abs/" + quote(arxiv_id, safe="/")


def arxiv_pdf_url(arxiv_id: str) -> str:
    arxiv_id = normalize_arxiv_id(arxiv_id) or arxiv_id
    return "https://arxiv.org/pdf/" + quote(arxiv_id, safe="/") + ".pdf"


def doi_landing_url(doi: str) -> str:
    return "https://doi.org/" + doi.strip()


def host_of(url: str | None) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower().removeprefix("www.")


def openreview_pdf_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "openreview.net" not in parsed.netloc:
        return None
    qs = parse_qs(parsed.query)
    paper_id = (qs.get("id") or [None])[0]
    if not paper_id:
        return None
    return f"https://openreview.net/pdf?id={quote(paper_id)}"


def acl_pdf_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "aclanthology.org" not in parsed.netloc:
        return None
    path = parsed.path.strip("/")
    if not path:
        return None
    if path.endswith(".pdf"):
        return url
    paper_id = path.split("/")[0]
    if re.match(r"^[A-Z]\d{2}-\d{4}$|^\d{4}\.[a-z-]+\.\d+$", paper_id, re.I):
        return f"https://aclanthology.org/{paper_id}.pdf"
    return None


def acm_doi_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "dl.acm.org" not in host:
        return None
    path = unquote(parsed.path).strip("/")
    for prefix in ("doi/pdf/", "doi/abs/", "doi/fullHtml/", "doi/"):
        if path.startswith(prefix):
            return path[len(prefix):].strip() or None
    return extract_doi(url)


def acm_landing_url(doi: str) -> str:
    return "https://dl.acm.org/doi/" + quote(doi.strip(), safe="/")


def acm_pdf_url(url: str) -> str | None:
    doi = acm_doi_from_url(url)
    if not doi:
        return None
    return "https://dl.acm.org/doi/pdf/" + quote(doi, safe="/")
