from __future__ import annotations

from ..models import PaperCandidate, SearchPlan


class CandidateResolver:
    def __init__(self, providers):
        self.providers = list(providers)

    async def resolve(self, plan: SearchPlan) -> list[PaperCandidate]:
        candidates: list[PaperCandidate] = []
        for provider in self.providers:
            candidates.extend(await provider.resolve(plan))
        return candidates
