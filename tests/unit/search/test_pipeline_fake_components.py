from __future__ import annotations

import asyncio

from paperos.config import load_config
from paperos.search.models import (
    FulltextLocation,
    FulltextStatus,
    HypothesisKind,
    PaperCandidate,
    PaperHypothesis,
    SearchIntent,
    SearchPlan,
)
from paperos.search.pipeline import PaperSearchPipeline
from paperos.search.resolve.dedup import PaperDeduplicator
from paperos.search.resolve.disambiguator import PaperDisambiguator
from tests.support.fakes import FakeQueryAnalyzer


class FakeCrawler:
    def __init__(self, candidates):
        self.candidates = candidates
        self.closed = False

    async def discover(self, plan):
        return list(self.candidates)

    async def aclose(self):
        self.closed = True


class FakeVerifier:
    def __init__(self, *, verify_pdf: bool = True):
        self.verify_pdf = verify_pdf
        self.closed = False

    async def verify(self, loc, paper):
        if self.verify_pdf:
            loc.status = FulltextStatus.VERIFIED_PDF
            loc.local_path = "C:/tmp/paper.pdf"
            loc.filename = "paper.pdf"
            loc.sha256 = "a" * 64
            loc.page_count = 12
        else:
            loc.status = FulltextStatus.INVALID
            loc.reason = "test invalid"
        return loc

    async def aclose(self):
        self.closed = True


def _plan() -> SearchPlan:
    return SearchPlan(
        raw_query="attention is all you need",
        intent=SearchIntent.FIND_SPECIFIC,
        hypotheses=[
            PaperHypothesis(
                kind=HypothesisKind.DOI,
                confidence=1.0,
                title="Attention Is All You Need",
                doi="10.5555/attention",
            )
        ],
        final_limit=1,
        need_fulltext=True,
    )


def test_pipeline_selects_candidate_and_verifies_pdf():
    async def run():
        cfg = load_config({"search_policy": {"accept_min_score": 0.7}})
        candidate = PaperCandidate(
            title="Attention Is All You Need",
            doi="10.5555/attention",
            fulltext_locations=[FulltextLocation(url="https://example.test/paper.pdf", source="test")],
            source="test",
        )
        pipeline = PaperSearchPipeline(
            cfg=cfg,
            query_analyzer=FakeQueryAnalyzer(_plan()),
            crawler=FakeCrawler([candidate]),
            deduplicator=PaperDeduplicator(),
            disambiguator=PaperDisambiguator(cfg.search_policy),
            verifier=FakeVerifier(),
        )

        result = await pipeline.run("attention is all you need", need_fulltext=True)

        assert result.status == "selected"
        assert result.selected
        assert result.selected[0].best_verified_pdf() is not None

    asyncio.run(run())


def test_pipeline_returns_not_found_when_fulltext_required_but_invalid():
    async def run():
        cfg = load_config({})
        candidate = PaperCandidate(
            title="Attention Is All You Need",
            doi="10.5555/attention",
            fulltext_locations=[FulltextLocation(url="https://example.test/not-pdf", source="test")],
            source="test",
        )
        pipeline = PaperSearchPipeline(
            cfg=cfg,
            query_analyzer=FakeQueryAnalyzer(_plan()),
            crawler=FakeCrawler([candidate]),
            deduplicator=PaperDeduplicator(),
            disambiguator=PaperDisambiguator(cfg.search_policy),
            verifier=FakeVerifier(verify_pdf=False),
        )

        result = await pipeline.run("attention is all you need", need_fulltext=True)

        assert result.status == "not_found"
        assert "no candidate URL was verified as PDF" in result.message

    asyncio.run(run())

