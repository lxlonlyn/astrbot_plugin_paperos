from __future__ import annotations

import re

from ..models import PaperCandidate


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


class PaperDeduplicator:
    def dedup(self, candidates: list[PaperCandidate]) -> list[PaperCandidate]:
        by_key: dict[str, PaperCandidate] = {}
        for cand in candidates:
            key = self._key(cand)
            if not key:
                continue
            old = by_key.get(key)
            if old is None or self._quality(cand) > self._quality(old):
                if old is not None:
                    cand.fulltext_locations = old.fulltext_locations + cand.fulltext_locations
                by_key[key] = cand
        return list(by_key.values())

    def _key(self, cand: PaperCandidate) -> str:
        if cand.doi:
            return "doi:" + cand.doi.lower()
        if cand.arxiv_id:
            return "arxiv:" + cand.arxiv_id.lower()
        if cand.core_id:
            return "core:" + cand.core_id
        return "title:" + normalize_title(cand.title)

    def _quality(self, cand: PaperCandidate) -> float:
        score = cand.score
        if cand.doi:
            score += 0.2
        if cand.download_url:
            score += 0.1
        if cand.abstract:
            score += 0.05
        if cand.citation_count:
            score += min(cand.citation_count, 1000) / 10000
        return score
