from astrbot.api import logger

from ..models import FulltextLocation, PaperCandidate
from ..providers.base import FulltextProvider


class FulltextResolver:
    def __init__(self, providers: list[FulltextProvider]):
        self.providers = providers

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        all_locations: list[FulltextLocation] = []
        for provider in self.providers:
            locations = await provider.resolve(paper)
            logger.debug(
                "[PaperOS][FulltextResolver] provider=%s paper=%s locations=%d",
                provider.name,
                self._short_title(paper.title),
                len(locations),
            )
            all_locations.extend(locations)
        return self._dedup(all_locations)

    def _dedup(self, locations: list[FulltextLocation]) -> list[FulltextLocation]:
        seen: set[str] = set()
        out: list[FulltextLocation] = []
        for loc in locations:
            if loc.url not in seen:
                seen.add(loc.url)
                out.append(loc)
        return sorted(out, key=lambda x: x.confidence, reverse=True)

    def _short_title(self, title: str) -> str:
        return title if len(title) <= 70 else title[:67] + "..."

    async def aclose(self) -> None:
        for provider in self.providers:
            await provider.aclose()
