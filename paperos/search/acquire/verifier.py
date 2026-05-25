from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx
from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ...config import SearchPolicyConfig
from ..models import FulltextLocation, FulltextStatus, PaperCandidate


PLUGIN_NAME = "astrbot_plugin_paperos"


class FulltextVerifier:
    """Strict PDF verifier for PaperOS searcher."""

    def __init__(self, policy: SearchPolicyConfig):
        self.policy = policy

        timeout = float(getattr(policy, "download_timeout_seconds", 60) or 60)
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

        self.download_dir = (
            Path(get_astrbot_data_path())
            / "plugin_data"
            / PLUGIN_NAME
            / "searcher"
            / "fulltext"
        )
        self.download_dir.mkdir(parents=True, exist_ok=True)

        max_mb = int(getattr(policy, "max_pdf_size_mb", 100) or 100)
        self.max_bytes = max(1, max_mb) * 1024 * 1024

    async def verify(self, loc: FulltextLocation, paper: PaperCandidate) -> FulltextLocation:
        if not self.policy.enable_fulltext_verify:
            return loc

        if not loc.url.lower().startswith(("http://", "https://")):
            return self._fail(loc, FulltextStatus.INVALID, "unsupported URL scheme")

        logger.debug(
            "[PaperOS][FulltextVerifier] download_start paper=%s source=%s reason=%s url=%s",
            self._short(paper.title),
            loc.source,
            loc.reason,
            loc.url,
        )

        try:
            downloaded = await self._download_pdf_candidate(loc, paper)
        except _AuthRequired as exc:
            return self._fail(loc, FulltextStatus.REQUIRES_AUTH, str(exc))
        except _NotPdfResponse as exc:
            loc.kind = "landing"
            loc.content_type = exc.content_type
            return self._fail(loc, FulltextStatus.NO_OPEN_ACCESS, exc.reason)
        except _DownloadRejected as exc:
            return self._fail(loc, FulltextStatus.INVALID, str(exc))
        except httpx.HTTPError as exc:
            logger.debug("[PaperOS][FulltextVerifier] http_failed url=%s error=%s", loc.url, exc)
            return self._fail(loc, FulltextStatus.FAILED, f"http error: {exc}")
        except Exception as exc:
            logger.debug("[PaperOS][FulltextVerifier] download_failed url=%s error=%s", loc.url, exc)
            return self._fail(loc, FulltextStatus.FAILED, f"download error: {exc}")

        validation_error, page_count = self._validate_local_pdf(downloaded.path)
        if validation_error:
            downloaded.path.unlink(missing_ok=True)
            return self._fail(loc, FulltextStatus.INVALID, validation_error)

        loc.status = FulltextStatus.VERIFIED_PDF
        loc.kind = "pdf"
        loc.reason = "downloaded to plugin_data and validated as local PDF"
        loc.local_path = str(downloaded.path)
        loc.final_url = downloaded.final_url
        loc.filename = downloaded.path.name
        loc.sha256 = downloaded.sha256
        loc.size_bytes = downloaded.size_bytes
        loc.content_type = downloaded.content_type
        loc.page_count = page_count

        logger.debug(
            "[PaperOS][FulltextVerifier] download_ok paper=%s file=%s size=%s sha256=%s pages=%s",
            self._short(paper.title),
            loc.local_path,
            loc.size_bytes,
            (loc.sha256 or "")[:12],
            loc.page_count,
        )
        return loc

    async def _download_pdf_candidate(self, loc: FulltextLocation, paper: PaperCandidate) -> "_DownloadedPDF":
        headers = {
            "Accept": "application/pdf,*/*;q=0.5",
            "User-Agent": "PaperOS/0.1 (+https://github.com/lxlonlyn/astrbot_plugin_paperos)",
        }
        headers.update(loc.request_headers or {})

        async with self._client.stream("GET", loc.url, headers=headers) as resp:
            loc.final_url = str(resp.url)
            content_type = resp.headers.get("content-type", "").lower()
            loc.content_type = content_type

            if resp.status_code in {401, 403}:
                raise _AuthRequired(f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                raise _DownloadRejected(f"HTTP {resp.status_code}")

            content_length = self._parse_int(resp.headers.get("content-length"))
            if content_length is not None and content_length > self.max_bytes:
                raise _DownloadRejected(
                    f"file too large by content-length: {content_length} > {self.max_bytes}"
                )

            safe_stem = self._safe_stem(paper, loc)
            partial_path = self.download_dir / f"{safe_stem}.part"

            sha256 = hashlib.sha256()
            size = 0
            prefix = bytearray()

            with partial_path.open("wb") as f:
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue

                    if len(prefix) < 4096:
                        prefix.extend(chunk[: 4096 - len(prefix)])

                    size += len(chunk)
                    if size > self.max_bytes:
                        partial_path.unlink(missing_ok=True)
                        raise _DownloadRejected(
                            f"file too large while downloading: {size} > {self.max_bytes}"
                        )

                    sha256.update(chunk)
                    f.write(chunk)

            if size == 0:
                partial_path.unlink(missing_ok=True)
                raise _DownloadRejected("empty response")

            prefix_bytes = bytes(prefix).lstrip()
            if self._looks_like_html(prefix_bytes, content_type):
                partial_path.unlink(missing_ok=True)
                raise _NotPdfResponse(
                    content_type=content_type,
                    reason="candidate returned HTML/landing page, not PDF",
                )

            if not prefix_bytes.startswith(b"%PDF-"):
                partial_path.unlink(missing_ok=True)
                raise _NotPdfResponse(
                    content_type=content_type,
                    reason=f"candidate is not a PDF; content-type={content_type or 'unknown'}",
                )

            digest = sha256.hexdigest()
            final_path = self.download_dir / f"{digest}.pdf"

            if final_path.exists():
                partial_path.unlink(missing_ok=True)
            else:
                partial_path.replace(final_path)

            return _DownloadedPDF(
                path=final_path,
                final_url=str(resp.url),
                sha256=digest,
                size_bytes=size,
                content_type=content_type or None,
            )

    def _validate_local_pdf(self, path: Path) -> tuple[str | None, int | None]:
        try:
            with path.open("rb") as f:
                if not f.read(8).startswith(b"%PDF-"):
                    return "downloaded local file does not start with %PDF-", None

            reader = PdfReader(str(path))
            page_count = len(reader.pages)
            if page_count <= 0:
                return "downloaded PDF has zero pages", None
            return None, page_count
        except PdfReadError as exc:
            return f"pypdf rejected downloaded file: {exc}", None
        except Exception as exc:
            return f"local PDF validation failed: {exc}", None

    def _looks_like_html(self, prefix: bytes, content_type: str) -> bool:
        if "text/html" in content_type:
            return True
        sample = prefix[:512].lower()
        return sample.startswith(b"<!doctype html") or sample.startswith(b"<html")

    def _safe_stem(self, paper: PaperCandidate, loc: FulltextLocation) -> str:
        base = paper.doi or paper.arxiv_id or paper.core_id or paper.title or "paper"
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")[:80] or "paper"
        url_hash = hashlib.sha1(loc.url.encode("utf-8", errors="ignore")).hexdigest()[:10]
        return f"{base}_{url_hash}"

    def _parse_int(self, value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _fail(self, loc: FulltextLocation, status: FulltextStatus, reason: str) -> FulltextLocation:
        loc.status = status
        loc.reason = reason
        loc.local_path = None
        loc.filename = None
        loc.sha256 = None
        loc.size_bytes = None
        loc.page_count = None
        logger.debug(
            "[PaperOS][FulltextVerifier] not_verified url=%s status=%s reason=%s",
            loc.url,
            status.value,
            reason,
        )
        return loc

    def _short(self, title: str, limit: int = 70) -> str:
        return title if len(title) <= limit else title[: limit - 3] + "..."

    async def aclose(self) -> None:
        await self._client.aclose()


class _DownloadRejected(Exception):
    pass


class _AuthRequired(Exception):
    pass


class _NotPdfResponse(Exception):
    def __init__(self, *, content_type: str, reason: str):
        super().__init__(reason)
        self.content_type = content_type
        self.reason = reason


class _DownloadedPDF:
    def __init__(
        self,
        *,
        path: Path,
        final_url: str,
        sha256: str,
        size_bytes: int,
        content_type: str | None,
    ):
        self.path = path
        self.final_url = final_url
        self.sha256 = sha256
        self.size_bytes = size_bytes
        self.content_type = content_type
