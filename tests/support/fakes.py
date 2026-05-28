from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeEvent:
    message_str: str = ""
    unified_msg_origin: str = "test-origin"


class FakeLLMContext:
    def __init__(self, completion_text: str, *, current_provider_id: str = "provider-from-event"):
        self.completion_text = completion_text
        self.current_provider_id = current_provider_id
        self.llm_calls: list[dict[str, Any]] = []
        self.provider_requests: list[Any] = []

    async def get_current_chat_provider_id(self, umo=None) -> str:
        self.provider_requests.append(umo)
        return self.current_provider_id

    async def llm_generate(self, **kwargs):
        self.llm_calls.append(kwargs)
        return SimpleNamespace(completion_text=self.completion_text)


class FakeQueryAnalyzer:
    def __init__(self, plan):
        self.plan = plan
        self.calls: list[str] = []

    async def analyze(self, raw_query: str, *, event=None):
        self.calls.append(raw_query)
        return self.plan

    async def repair(self, raw_query: str, previous_plan, failure_reason: str, *, event=None):
        return previous_plan

