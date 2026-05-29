from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..models import FulltextLocation, PaperCandidate


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    title = re.sub(r"^\s*\[(?:pdf|html|arxiv)\]\s*", "", title, flags=re.I)
    title = re.sub(r"\.\.\.$", "", title.strip())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


class PaperDeduplicator:
    def dedup(self, candidates: list[PaperCandidate]) -> list[PaperCandidate]:
        out: list[PaperCandidate] = []
        for cand in candidates:
            if not self._key(cand):
                continue
            existing = self._find_duplicate(out, cand)
            if existing is None:
                out.append(cand)
                continue
            survivor = self._merge(existing, cand)
            if survivor is not existing:
                out[out.index(existing)] = survivor
        return out

    def _key(self, cand: PaperCandidate) -> str:
        if cand.doi:
            return "doi:" + cand.doi.lower()
        if cand.arxiv_id:
            return "arxiv:" + cand.arxiv_id.lower()
        if cand.core_id:
            return "core:" + cand.core_id
        return "title:" + normalize_title(cand.title)

    def _find_duplicate(
        self,
        existing: list[PaperCandidate],
        cand: PaperCandidate,
    ) -> PaperCandidate | None:
        cand_key = self._key(cand)
        for old in existing:
            old_key = self._key(old)
            if cand_key == old_key:
                return old
            if self._same_paper_by_title(old, cand):
                return old
        return None

    def _same_paper_by_title(self, a: PaperCandidate, b: PaperCandidate) -> bool:
        ta = normalize_title(a.title)
        tb = normalize_title(b.title)
        if len(ta) < 12 or len(tb) < 12:
            return False

        # Keep strong identifiers authoritative. Different known identifiers mean
        # the titles should not merge unless another id already matched above.
        if a.doi and b.doi and a.doi.lower() != b.doi.lower():
            return False
        if a.arxiv_id and b.arxiv_id and a.arxiv_id.lower() != b.arxiv_id.lower():
            return False
        if a.core_id and b.core_id and a.core_id != b.core_id:
            return False

        ratio = SequenceMatcher(None, ta, tb).ratio()
        if ratio >= 0.90:
            return True

        a_tokens = self._title_tokens(ta)
        b_tokens = self._title_tokens(tb)
        if len(a_tokens) < 5 or len(b_tokens) < 5:
            return False
        overlap = len(a_tokens & b_tokens) / max(1, min(len(a_tokens), len(b_tokens)))
        containment = ta in tb or tb in ta
        return overlap >= 0.86 and (containment or ratio >= 0.74)

    def _merge(self, old: PaperCandidate, cand: PaperCandidate) -> PaperCandidate:
        survivor, other = (cand, old) if self._quality(cand) > self._quality(old) else (old, cand)

        survivor.fulltext_locations = self._dedup_locations(
            survivor.fulltext_locations + other.fulltext_locations
        )
        survivor.download_url = survivor.download_url or other.download_url
        survivor.landing_url = survivor.landing_url or other.landing_url
        survivor.doi = survivor.doi or other.doi
        survivor.arxiv_id = survivor.arxiv_id or other.arxiv_id
        survivor.core_id = survivor.core_id or other.core_id
        survivor.openalex_id = survivor.openalex_id or other.openalex_id
        survivor.semantic_scholar_id = survivor.semantic_scholar_id or other.semantic_scholar_id
        survivor.authors = survivor.authors or other.authors
        survivor.year = survivor.year or other.year
        survivor.venue = survivor.venue or other.venue
        survivor.publisher = survivor.publisher or other.publisher
        survivor.abstract = survivor.abstract or other.abstract
        survivor.raw.setdefault("paperos_merged_duplicates", [])
        survivor.raw["paperos_merged_duplicates"].append(
            {
                "title": other.title,
                "source": other.source,
                "landing_url": other.landing_url,
                "download_url": other.download_url,
            }
        )
        return survivor

    def _dedup_locations(self, locations: list[FulltextLocation]) -> list[FulltextLocation]:
        by_url: dict[str, FulltextLocation] = {}
        for loc in locations:
            old = by_url.get(loc.url)
            if old is None or loc.confidence > old.confidence:
                by_url[loc.url] = loc
        return sorted(by_url.values(), key=lambda x: x.confidence, reverse=True)

    def _title_tokens(self, title: str) -> set[str]:
        stop = {"a", "an", "and", "for", "of", "on", "the", "to", "with", "in"}
        return {token for token in title.split() if len(token) > 1 and token not in stop}

    def _quality(self, cand: PaperCandidate) -> float:
        score = cand.score
        if cand.arxiv_id:
            score += 0.25
        if cand.doi:
            score += 0.2
        if cand.download_url:
            score += 0.1
        if cand.fulltext_locations:
            score += 0.05
        if cand.abstract:
            score += 0.05
        if cand.citation_count:
            score += min(cand.citation_count, 1000) / 10000
        return score
