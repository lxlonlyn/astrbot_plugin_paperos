import httpx
from astrbot.api import logger

from ...config import SearchPolicyConfig
from ..models import FulltextLocation, FulltextStatus, PaperCandidate


class FulltextVerifier:
    """Lightweight verifier for fulltext candidates.

    It does not bypass paywalls. It only checks whether the candidate URL is a
    PDF, HTML article page, landing page, or an unavailable/auth-required URL.
    """

    def __init__(self, policy: SearchPolicyConfig):
        self.policy = policy
        self._client = httpx.AsyncClient(timeout=20, follow_redirects=True)

    async def verify(self, loc: FulltextLocation, paper: PaperCandidate) -> FulltextLocation:
        if not self.policy.enable_fulltext_verify:
            return loc
        if not loc.url.lower().startswith(("http://", "https://")):
            loc.status = FulltextStatus.INVALID
            loc.reason = "unsupported URL scheme"
            return loc

        try:
            resp = await self._client.get(
                loc.url,
                headers={"Range": "bytes=0-4095", "Accept": "application/pdf,text/html,*/*"},
            )
        except httpx.HTTPError as exc:
            loc.status = FulltextStatus.FAILED
            loc.reason = f"http error: {exc}"
            logger.debug("[PaperOS][FulltextVerifier] failed url=%s error=%s", loc.url, exc)
            return loc

        content_type = resp.headers.get("content-type", "").lower()
        prefix = resp.content[:16]
        if resp.status_code in {401, 403}:
            loc.status = FulltextStatus.REQUIRES_AUTH
            loc.reason = f"HTTP {resp.status_code}"
        elif resp.status_code >= 400:
            loc.status = FulltextStatus.FAILED
            loc.reason = f"HTTP {resp.status_code}"
        elif prefix.startswith(b"%PDF-") or "application/pdf" in content_type:
            loc.status = FulltextStatus.VERIFIED_PDF
            loc.kind = "pdf"
            loc.reason = "verified by content-type or PDF magic bytes"
        elif "text/html" in content_type:
            loc.status = FulltextStatus.HTML_FULLTEXT if self._looks_like_article_html(resp.text[:4096]) else FulltextStatus.LANDING_ONLY
            loc.kind = "html" if loc.status == FulltextStatus.HTML_FULLTEXT else "landing"
            loc.reason = "html response"
        else:
            loc.status = FulltextStatus.INVALID
            loc.reason = f"unrecognized content-type={content_type or 'unknown'}"

        logger.debug(
            "[PaperOS][FulltextVerifier] paper=%s url=%s status=%s reason=%s",
            self._short(paper.title),
            loc.url,
            loc.status.value,
            loc.reason,
        )
        return loc

    def _looks_like_article_html(self, text: str) -> bool:
        low = text.lower()
        return any(marker in low for marker in ("citation", "abstract", "references", "article", "doi"))

    def _short(self, title: str) -> str:
        return title if len(title) <= 70 else title[:67] + "..."

    async def aclose(self) -> None:
        await self._client.aclose()
