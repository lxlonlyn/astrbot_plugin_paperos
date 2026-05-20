from __future__ import annotations

from ...config import SearchPolicyConfig
from ..models import PaperCandidate, SearchIntent, SearchPlan


class PaperDisambiguator:
    def __init__(self, policy: SearchPolicyConfig):
        self.policy = policy

    def select(self, plan: SearchPlan, candidates: list[PaperCandidate]) -> list[PaperCandidate]:
        if not candidates:
            return []
        if plan.intent in {SearchIntent.TOPIC_DISCOVERY, SearchIntent.FIND_MULTIPLE, SearchIntent.EXPAND_RELATED}:
            return candidates[: plan.final_limit]

        top1 = candidates[0]
        top2 = candidates[1] if len(candidates) > 1 else None
        if top1.score < self.policy.accept_min_score:
            return []
        if top2 is not None and (top1.score - top2.score) < self.policy.ambiguous_gap_threshold:
            return []
        return [top1]
