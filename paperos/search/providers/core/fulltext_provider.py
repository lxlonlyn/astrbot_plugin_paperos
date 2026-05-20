from __future__ import annotations

from ...models import FulltextLocation, PaperCandidate
from .client import CoreClient


class CoreFulltextProvider:
    name = "core"

    def __init__(self, client: CoreClient):
        self.client = client

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        locations: list[FulltextLocation] = []
        if paper.download_url:
            locations.append(
                FulltextLocation(
                    url=paper.download_url,
                    source="core",
                    kind="pdf",
                    confidence=0.8,
                )
            )
        if paper.landing_url:
            locations.append(
                FulltextLocation(
                    url=paper.landing_url,
                    source="core",
                    kind="landing",
                    confidence=0.4,
                )
            )
        return locations
