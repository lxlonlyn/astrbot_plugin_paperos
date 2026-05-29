from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

from astrbot.api import logger

from ...config import PaperOSConfig
from ..models import HypothesisKind, PaperHypothesis, SearchIntent
from .fallback import fallback_analyze
from .prompts import (
    build_query_analyzer_prompt,
    build_repair_prompt,
)
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

        use_web_search = self._should_use_astrbot_web_search(event)
        prompt = build_query_analyzer_prompt(raw_query)
        try:
            resp = await self._generate(provider_id=provider_id, prompt=prompt)
            data = self._extract_json(resp.completion_text)
            plan = parse_search_plan(
                data,
                raw_query=raw_query,
                max_hypotheses=self.cfg.query_analyzer.max_hypotheses,
            )
            if not plan.hypotheses:
                return fallback_analyze(raw_query)
            if use_web_search:
                await self._augment_plan_with_astrbot_web_search(plan, event=event)
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
            use_web_search = self._should_use_astrbot_web_search(event)
            prompt = build_repair_prompt(raw_query, previous_json, failure_reason)
            resp = await self._generate(provider_id=provider_id, prompt=prompt)
            data = self._extract_json(resp.completion_text)
            plan = parse_search_plan(data, raw_query=raw_query, max_hypotheses=self.cfg.query_analyzer.max_hypotheses)
            if use_web_search:
                await self._augment_plan_with_astrbot_web_search(plan, event=event)
            return plan
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

    async def _generate(self, *, provider_id: str, prompt: str):
        return await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
        )

    def _should_use_astrbot_web_search(self, event: Any | None) -> bool:
        if event is None or not hasattr(self.context, "get_config"):
            return False
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
            return bool(provider_settings.get("web_search", False))
        except Exception as exc:
            logger.debug("[PaperOS] failed to inspect AstrBot web_search config: %r", exc)
            return False

    def _build_astrbot_web_search_tool(self, event: Any):
        try:
            from astrbot.core.tools.web_search_tools import normalize_legacy_web_search_config
        except Exception as exc:
            logger.debug("[PaperOS] AstrBot web search tool imports unavailable: %r", exc)
            normalize_legacy_web_search_config = None

        if not hasattr(self.context, "get_config") or not hasattr(self.context, "get_llm_tool_manager"):
            return None

        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            if normalize_legacy_web_search_config is not None:
                normalize_legacy_web_search_config(cfg)
            provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
            if not provider_settings.get("web_search", False):
                return None

            provider = provider_settings.get("websearch_provider", "tavily")
            tool_names_by_provider = {
                "tavily": "web_search_tavily",
                "bocha": "web_search_bocha",
                "brave": "web_search_brave",
                "firecrawl": "web_search_firecrawl",
                "baidu_ai_search": "web_search_baidu",
            }
            tool_name = tool_names_by_provider.get(provider)
            if not tool_name:
                logger.debug("[PaperOS] unsupported AstrBot websearch_provider=%r", provider)
                return None

            tool_mgr = self.context.get_llm_tool_manager()
            return provider, tool_mgr.get_builtin_tool(tool_name)
        except Exception as exc:
            logger.debug("[PaperOS] failed to build AstrBot web search tool: %r", exc)
            return None

    async def _augment_plan_with_astrbot_web_search(self, plan: SearchPlan, *, event: Any | None) -> None:
        if event is None or self.cfg.query_analyzer.max_web_search_queries <= 0:
            return
        built = self._build_astrbot_web_search_tool(event)
        if not built:
            return
        provider, tool = built
        queries = self._web_search_queries(plan)
        if not queries:
            return

        ctx = SimpleNamespace(
            context=SimpleNamespace(context=self.context, event=event),
            tool_call_timeout=60,
        )
        evidence: list[dict[str, Any]] = []
        existing_urls = {h.url for h in plan.hypotheses if h.url}
        success_count = 0
        failure_count = 0

        total_queries = len(queries)
        for idx, query in enumerate(queries, start=1):
            try:
                kwargs = self._web_search_kwargs(provider, query)
                logger.debug(
                    "[PaperOS] AstrBot web search provider=%s query=%d/%d %r",
                    provider,
                    idx,
                    total_queries,
                    query,
                )
                result = await tool.call(ctx, **kwargs)
                rows = self._parse_web_search_result(str(result), query=query)
            except Exception as exc:
                failure_count += 1
                logger.warning(
                    "[PaperOS] AstrBot web search failed provider=%s query=%d/%d %r: %r",
                    provider,
                    idx,
                    total_queries,
                    query,
                    exc,
                )
                continue
            success_count += 1
            logger.debug(
                "[PaperOS] AstrBot web search result provider=%s query=%d/%d rows=%d",
                provider,
                idx,
                total_queries,
                len(rows),
            )
            evidence.extend(rows)
            for row in rows[:5]:
                url = row.get("url")
                if not url or url in existing_urls:
                    continue
                existing_urls.add(url)
                plan.hypotheses.append(
                    PaperHypothesis(
                        kind=HypothesisKind.URL,
                        confidence=0.72,
                        title=row.get("title") or None,
                        url=url,
                        search_queries=[query],
                        note=f"AstrBot {provider} web search evidence",
                    )
                )

        if evidence:
            plan.raw_llm_output.setdefault("web_search", {})
            plan.raw_llm_output["web_search"] = {
                "provider": provider,
                "query_count": len(queries),
                "queries": queries,
                "results": evidence[:25],
            }
            logger.debug(
                "[PaperOS] QueryAnalyzer added %d AstrBot web-search evidence rows from %d queries",
                len(evidence),
                len(queries),
            )
        logger.debug(
            "[PaperOS] AstrBot web search done provider=%s planned=%d success=%d failed=%d evidence_rows=%d",
            provider,
            total_queries,
            success_count,
            failure_count,
            len(evidence),
        )

    def _web_search_queries(self, plan: SearchPlan) -> list[str]:
        limit = min(max(self.cfg.query_analyzer.max_web_search_queries, 0), 5)
        if limit <= 0:
            return []

        raw: list[str] = []
        for hyp in plan.hypotheses:
            title = (hyp.translated_title or hyp.title or "").strip()
            if title:
                raw.append(f'"{title}"')
                if hyp.authors:
                    raw.append(f'"{title}" {" ".join(hyp.authors[:2])}')
                if hyp.venue:
                    raw.append(f'"{title}" "{hyp.venue}"')
            raw.extend(q.strip() for q in hyp.search_queries if q and q.strip())
            if hyp.doi:
                raw.append(hyp.doi)
            if hyp.arxiv_id:
                raw.append(f"arxiv {hyp.arxiv_id}")

        if plan.translated_query:
            raw.append(plan.translated_query.strip())
        raw.extend(k.strip() for k in plan.topic_keywords if k and k.strip())
        if not _contains_cjk(plan.raw_query):
            raw.append(plan.raw_query.strip())

        # Specific-paper queries usually need fewer probes, but keep the hard cap at 5.
        if plan.intent in {SearchIntent.FIND_SPECIFIC, SearchIntent.DOWNLOAD_KNOWN}:
            limit = min(limit, 3)

        out: list[str] = []
        seen: set[str] = set()
        for query in raw:
            query = _clean_query(query)
            if not query or _contains_cjk(query):
                continue
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(query)
            if len(out) >= limit:
                break
        return out

    def _web_search_kwargs(self, provider: str, query: str) -> dict[str, Any]:
        if provider == "tavily":
            return {"query": query, "max_results": 5, "search_depth": "basic", "topic": "general"}
        if provider == "bocha":
            return {"query": query, "count": 5, "summary": False}
        if provider == "brave":
            return {"query": query, "count": 5, "country": "US", "search_lang": "en"}
        if provider == "firecrawl":
            return {"query": query, "limit": 5, "country": "US"}
        if provider == "baidu_ai_search":
            return {"query": query, "top_k": 5}
        return {"query": query}

    def _parse_web_search_result(self, text: str, *, query: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            for item in data["results"]:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                if url:
                    rows.append(
                        {
                            "query": query,
                            "url": url,
                            "title": str(item.get("title", "")).strip(),
                            "snippet": str(item.get("snippet", "")).strip(),
                        }
                    )
            return rows

        for url in re.findall(r"https?://[^\s\"'<>]+", text):
            rows.append({"query": query, "url": url.rstrip(").,]"), "title": "", "snippet": ""})
        return rows

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


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())
