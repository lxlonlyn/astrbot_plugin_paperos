from __future__ import annotations

import httpx
from astrbot.api import logger

from ...config import SearchPolicyConfig
from ..models import FulltextLocation, FulltextStatus, PaperCandidate


class FulltextVerifier:
    def __init__(self, policy: SearchPolicyConfig):
        self.policy = policy

    async def verify(self, loc: FulltextLocation, paper: PaperCandidate) -> FulltextLocation:
        if not self.policy.enable_fulltext_verify:
            return loc
        if loc.kind == "landing":
            loc.status = FulltextStatus.LANDING_ONLY
            return loc
        if not loc.url.startswith(("http://", "https://")):
            loc.status = FulltextStatus.INVALID
            loc.reason = "unsupported URL scheme"
            return loc

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                # Some publishers block HEAD, so use a small Range GET.
                resp = await client.get(loc.url, headers={"Range": "bytes=0-4095", "Accept": "application/pdf,*/*"})
                ctype = resp.headers.get("content-type", "").lower()
                prefix = resp.content[:16]
                if resp.status_code in {401, 403}:
                    loc.status = FulltextStatus.REQUIRES_AUTH
                    loc.reason = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    loc.status = FulltextStatus.FAILED
                    loc.reason = f"HTTP {resp.status_code}"
                elif prefix.startswith(b"%PDF-") or "application/pdf" in ctype:
                    loc.status = FulltextStatus.VERIFIED_PDF
                    loc.kind = "pdf"
                    loc.reason = "PDF magic/content-type verified"
                elif "text/html" in ctype:
                    loc.status = FulltextStatus.HTML_FULLTEXT
                    loc.kind = "html"
                    loc.reason = "HTML response, not direct PDF"
                else:
                    loc.status = FulltextStatus.INVALID
                    loc.reason = f"unexpected content-type: {ctype}"
        except Exception as exc:
            logger.debug(f"[PaperOS] fulltext verify failed for {loc.url}: {exc!r}")
            loc.status = FulltextStatus.FAILED
            loc.reason = repr(exc)
        return loc
