from __future__ import annotations

from paperos.search.models import HypothesisKind, SearchContext, SearchIntent
from paperos.search.query.fallback import fallback_analyze
from paperos.search.query.schema import parse_search_plan


def test_parse_search_plan_clamps_candidates_and_defaults_zero_final_limit():
    plan = parse_search_plan(
        {
            "language": "zh",
            "intent": "topic_discovery",
            "hypotheses": [
                {
                    "kind": "arxiv",
                    "confidence": 1.5,
                    "title": "Attention Is All You Need",
                    "arxiv_id": "1706.03762",
                    "authors": ["Vaswani"],
                    "year": "2017",
                },
                {"kind": "unknown-kind", "confidence": -1},
            ],
            "max_candidates": 500,
            "final_limit": 0,
            "need_fulltext": True,
        },
        raw_query="attention",
        max_hypotheses=1,
    )

    assert plan.intent == SearchIntent.TOPIC_DISCOVERY
    assert plan.language == "zh"
    assert plan.max_candidates == 50
    assert plan.final_limit == 5
    assert len(plan.hypotheses) == 1
    assert plan.hypotheses[0].kind == HypothesisKind.ARXIV
    assert plan.hypotheses[0].confidence == 1.0


def test_fallback_analyze_extracts_known_identifiers():
    plan = fallback_analyze("please download arxiv:1706.03762 and doi:10.48550/arXiv.1706.03762")

    kinds = {hyp.kind for hyp in plan.hypotheses}
    assert HypothesisKind.ARXIV in kinds
    assert HypothesisKind.DOI in kinds
    assert plan.intent == SearchIntent.FIND_MULTIPLE
    assert plan.need_fulltext is True


def test_fallback_analyze_uses_search_context_hints():
    context = SearchContext(
        known_titles=["1-Lipschitz Neural Distance Fields"],
        known_identifiers=["arXiv:2407.09505"],
        expanded_queries=['"1-Lipschitz Neural Distance Fields" "Computer Graphics Forum"'],
    )

    plan = fallback_analyze("帮我找一下这篇论文", context=context)

    assert any(hyp.kind == HypothesisKind.ARXIV and hyp.arxiv_id == "2407.09505" for hyp in plan.hypotheses)
    title_hypotheses = [hyp for hyp in plan.hypotheses if hyp.kind == HypothesisKind.TITLE]
    assert title_hypotheses
    assert title_hypotheses[0].translated_title == "1-Lipschitz Neural Distance Fields"
    assert any("Computer Graphics Forum" in query for query in title_hypotheses[0].search_queries)
