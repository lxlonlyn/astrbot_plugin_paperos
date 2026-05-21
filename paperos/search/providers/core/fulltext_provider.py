from ..base import FulltextProvider
from ...models import FulltextLocation, PaperCandidate


class CoreFulltextProvider(FulltextProvider):
    name = "core"

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        locations: list[FulltextLocation] = []
        if paper.download_url:
            locations.append(
                FulltextLocation(
                    url=paper.download_url,
                    source=self.name,
                    kind="pdf",
                    confidence=0.75,
                    reason="CORE returned download_url",
                )
            )
        if paper.landing_url and paper.landing_url != paper.download_url:
            locations.append(
                FulltextLocation(
                    url=paper.landing_url,
                    source=self.name,
                    kind="landing",
                    confidence=0.35,
                    reason="CORE returned landing/source url",
                )
            )
        return locations

    async def aclose(self):
        pass