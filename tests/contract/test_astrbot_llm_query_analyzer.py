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


def test_llm_query_analyzer_directly_limits_astrbot_web_search_queries():
    async def run():
        completion = json.dumps(
            {
                "language": "en",
                "intent": "topic_discovery",
                "hypotheses": [
                    {
                        "kind": "topic",
                        "confidence": 0.8,
                        "search_queries": [
                            "Lipschitz regularization MLP",
                            "neural distance fields Lipschitz",
                            "signed distance functions Lipschitz neural networks",
                            "hKR loss neural fields",
                            "eikonal loss Lipschitz MLP",
                            "extra query should be capped",
                        ],
                    }
                ],
                "max_candidates": 10,
                "final_limit": 5,
                "need_fulltext": True,
            }
        )
        tool = FakeWebSearchTool()
        context = FakeWebSearchContext(completion, tool=tool)
        cfg = load_config({"query_analyzer": {"max_web_search_queries": 5}})
        analyzer = AstrBotLLMQueryAnalyzer(context=context, cfg=cfg)

        plan = await analyzer.analyze("将lipschitz条件融入到mlp，进行相关限制的文章", event=FakeEvent())

        assert len(tool.calls) == 5
        assert all("query" in call for call in tool.calls)
        assert all("extra query should be capped" not in call["query"] for call in tool.calls)
        assert all("将" not in call["query"] for call in tool.calls)
        assert any(h.kind == HypothesisKind.URL and h.url == "https://arxiv.org/abs/2407.09505" for h in plan.hypotheses)
        assert plan.raw_llm_output["web_search"]["query_count"] == 5

    asyncio.run(run())


class FakeWebSearchTool:
    name = "web_search_tavily"

    def __init__(self):
        self.calls = []

    async def call(self, context, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(
            {
                "results": [
                    {
                        "title": "1-Lipschitz Neural Distance Fields",
                        "url": "https://arxiv.org/abs/2407.09505",
                        "snippet": "arXiv paper page",
                    }
                ]
            }
        )


class FakeToolManager:
    def __init__(self, tool):
        self.tool = tool

    def get_builtin_tool(self, name):
        assert name == "web_search_tavily"
        return self.tool


class FakeWebSearchContext(FakeLLMContext):
    def __init__(self, completion_text: str, *, tool):
        super().__init__(completion_text, current_provider_id="provider-from-chat")
        self.tool = tool

    def get_config(self, umo=None):
        return {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "tavily",
                "websearch_tavily_key": ["test-key"],
            }
        }

    def get_llm_tool_manager(self):
        return FakeToolManager(self.tool)
