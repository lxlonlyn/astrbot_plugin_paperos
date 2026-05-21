from astrbot.api import logger

from ..models import PaperCandidate, SearchPlan
from ..providers.base import MetadataProvider


class CandidateResolver:
    def __init__(self, providers: list[MetadataProvider]):
        self.providers = providers

    async def resolve(self, plan: SearchPlan) -> list[PaperCandidate]:
        all_candidates: list[PaperCandidate] = []
        for provider in self.providers:
            logger.debug("[PaperOS][CandidateResolver] provider=%s start", provider.name)
            candidates = await provider.search(plan)
            logger.debug(
                "[PaperOS][CandidateResolver] provider=%s returned=%d sample=%s",
                provider.name,
                len(candidates),
                self._sample(candidates),
            )
            all_candidates.extend(candidates)
        return all_candidates

    def _sample(self, candidates: list[PaperCandidate], *, limit: int = 3) -> str:
        parts = []
        for cand in candidates[:limit]:
            title = cand.title if len(cand.title) <= 70 else cand.title[:67] + "..."
            parts.append(f"{title} ({cand.year or '?'})")
        suffix = "" if len(candidates) <= limit else f" ... +{len(candidates) - limit}"
        return "; ".join(parts) + suffix

    async def aclose(self) -> None:
        for provider in self.providers:
            await provider.aclose()
