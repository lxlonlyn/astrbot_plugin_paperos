from __future__ import annotations

import asyncio
import json

from paperos.config import load_config
from paperos.search.models import HypothesisKind, SearchIntent
from paperos.search.query.analyzer import AstrBotLLMQueryAnalyzer
from tests.support.fakes import FakeEvent, FakeLLMContext


def test_llm_query_analyzer_uses_event_provider_and_parses_json():
    async def run():
        completion = json.dumps(
            {
                "language": "en",
                "intent": "find_specific",
                "hypotheses": [
                    {
                        "kind": "arxiv",
                        "confidence": 0.95,
                        "title": "Attention Is All You Need",
                        "arxiv_id": "1706.03762",
                    }
                ],
                "max_candidates": 10,
                "final_limit": 1,
                "need_fulltext": True,
            }
        )
        context = FakeLLMContext(completion, current_provider_id="provider-from-chat")
        analyzer = AstrBotLLMQueryAnalyzer(context=context, cfg=load_config({}))

        plan = await analyzer.analyze("attention is all you need", event=FakeEvent())

        assert context.provider_requests == ["test-origin"]
        assert context.llm_calls[0]["chat_provider_id"] == "provider-from-chat"
        assert "prompt" in context.llm_calls[0]
        assert plan.intent == SearchIntent.FIND_SPECIFIC
        assert plan.hypotheses[0].kind == HypothesisKind.ARXIV
        assert plan.hypotheses[0].arxiv_id == "1706.03762"

    asyncio.run(run())


def test_llm_query_analyzer_falls_back_when_llm_returns_non_json():
    async def run():
        context = FakeLLMContext("not json", current_provider_id="provider-from-chat")
        analyzer = AstrBotLLMQueryAnalyzer(context=context, cfg=load_config({}))

        plan = await analyzer.analyze("10.1000/example", event=FakeEvent())

        assert plan.hypotheses
        assert plan.hypotheses[0].doi == "10.1000/example"

    asyncio.run(run())

