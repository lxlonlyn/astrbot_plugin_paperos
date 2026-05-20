from __future__ import annotations

from ..models import FulltextLocation, PaperCandidate


class FulltextResolver:
    def __init__(self, providers):
        self.providers = list(providers)

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        out: list[FulltextLocation] = []
        for provider in self.providers:
            out.extend(await provider.resolve(paper))
        return self._dedup(out)

    def _dedup(self, items: list[FulltextLocation]) -> list[FulltextLocation]:
        seen = set()
        out = []
        for item in items:
            key = item.url.strip()
            if key and key not in seen:
                seen.add(key)
                out.append(item)
        return out
