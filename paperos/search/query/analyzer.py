from __future__ import annotations

import json
from typing import Any

from astrbot.api import logger

from ...config import PaperOSConfig
from .fallback import fallback_analyze
from .prompts import build_query_analyzer_prompt, build_repair_prompt
from .schema import parse_search_plan
from ..models import SearchPlan


class AstrBotLLMQueryAnalyzer:
    """Use AstrBot's built-in LLM provider interface to build SearchPlan."""

    def __init__(self, *, context: Any, cfg: PaperOSConfig):
        self.context = context
        self.cfg = cfg

    async def analyze(self, raw_query: str, *, event: Any | None = None) -> SearchPlan:
        if not self.cfg.query_analyzer.enabled:
            return fallback_analyze(raw_query)

        provider_id = await self._resolve_provider_id(event)
        if not provider_id:
            logger.warning("[PaperOS] no LLM provider available; using fallback query analyzer")
            return fallback_analyze(raw_query)

        prompt = build_query_analyzer_prompt(raw_query)
        try:
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            logger.debug("[PaperOS] llm analysis result: {}".format(resp))

            data = self._extract_json(resp.completion_text)
            plan = parse_search_plan(
                data,
                raw_query=raw_query,
                max_hypotheses=self.cfg.query_analyzer.max_hypotheses,
            )

            if not plan.hypotheses:
                return fallback_analyze(raw_query)
            return plan
        except Exception as exc:
            logger.warning(f"[PaperOS] LLM query analyzer failed; fallback used: {exc!r}")
            return fallback_analyze(raw_query)

    async def repair(self, raw_query: str, previous_plan: SearchPlan, failure_reason: str, *, event: Any | None = None) -> SearchPlan:
        if not self.cfg.query_analyzer.enabled:
            return previous_plan
        provider_id = await self._resolve_provider_id(event)
        if not provider_id:
            return previous_plan
        try:
            previous_json = json.dumps(previous_plan.raw_llm_output or {}, ensure_ascii=False)
            prompt = build_repair_prompt(raw_query, previous_json, failure_reason)
            resp = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
            data = self._extract_json(resp.completion_text)
            return parse_search_plan(data, raw_query=raw_query, max_hypotheses=self.cfg.query_analyzer.max_hypotheses)
        except Exception as exc:
            logger.warning(f"[PaperOS] LLM query repair failed: {exc!r}")
            return previous_plan

    async def _resolve_provider_id(self, event: Any | None) -> str | None:
        configured = self.cfg.query_analyzer.provider_id or self.cfg.general.default_provider_id
        if configured:
            return configured
        if event is not None:
            try:
                return await self.context.get_current_chat_provider_id(umo=event.unified_msg_origin)
            except Exception as exc:
                logger.warning(f"[PaperOS] failed to get current chat provider id: {exc!r}")
        return None

    def _extract_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            raise ValueError(f"LLM did not return JSON: {text[:300]}")
        return json.loads(text[start : end + 1])
