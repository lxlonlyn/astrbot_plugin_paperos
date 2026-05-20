from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from ..models import FulltextLocation


class FulltextDownloader:
    """Reserved for later storage integration. Not used by the current command path."""

    async def download_pdf(self, loc: FulltextLocation, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(loc.url)
            resp.raise_for_status()
            digest = hashlib.sha256(resp.content).hexdigest()
            path = dest_dir / f"{digest}.pdf"
            path.write_bytes(resp.content)
            return path
