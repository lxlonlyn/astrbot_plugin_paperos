from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GeneralConfig:
    default_provider_id: str = ""
    thinking_provider_id: str = ""
    debug: bool = False


@dataclass(frozen=True)
class QueryAnalyzerConfig:
    enabled: bool = True
    provider_id: str = ""
    max_repair_rounds: int = 1
    max_hypotheses: int = 5


@dataclass(frozen=True)
class CoreAPIConfig:
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://api.core.ac.uk/v3"
    timeout_seconds: int = 25
    default_limit: int = 10
    topic_candidate_limit: int = 20
    sort: str = "relevance"


@dataclass(frozen=True)
class SearchPolicyConfig:
    accept_min_score: float = 0.78
    ambiguous_gap_threshold: float = 0.08
    max_return_candidates: int = 5
    enable_fulltext_verify: bool = True
    max_fulltext_candidates: int = 3


@dataclass(frozen=True)
class PaperOSConfig:
    general: GeneralConfig
    query_analyzer: QueryAnalyzerConfig
    core_api: CoreAPIConfig
    search_policy: SearchPolicyConfig


def _section(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    return value if isinstance(value, dict) else {}


def load_config(raw: Mapping[str, Any]) -> PaperOSConfig:
    """Convert AstrBotConfig/dict into typed PaperOSConfig."""
    general = _section(raw, "general")
    query_analyzer = _section(raw, "query_analyzer")
    core_api = _section(raw, "core_api")
    search_policy = _section(raw, "search_policy")

    return PaperOSConfig(
        general=GeneralConfig(
            default_provider_id=str(general.get("default_provider_id", "") or ""),
            thinking_provider_id=str(general.get("thinking_provider_id", "") or ""),
            debug=bool(general.get("debug", False)),
        ),
        query_analyzer=QueryAnalyzerConfig(
            enabled=bool(query_analyzer.get("enabled", True)),
            provider_id=str(query_analyzer.get("provider_id", "") or ""),
            max_repair_rounds=int(query_analyzer.get("max_repair_rounds", 1) or 1),
            max_hypotheses=int(query_analyzer.get("max_hypotheses", 5) or 5),
        ),
        core_api=CoreAPIConfig(
            enabled=bool(core_api.get("enabled", True)),
            api_key=str(core_api.get("api_key", "") or ""),
            base_url=str(core_api.get("base_url", "https://api.core.ac.uk/v3") or "https://api.core.ac.uk/v3").rstrip("/"),
            timeout_seconds=int(core_api.get("timeout_seconds", 25) or 25),
            default_limit=int(core_api.get("default_limit", 10) or 10),
            topic_candidate_limit=int(core_api.get("topic_candidate_limit", 20) or 20),
            sort=str(core_api.get("sort", "relevance") or "relevance"),
        ),
        search_policy=SearchPolicyConfig(
            accept_min_score=float(search_policy.get("accept_min_score", 0.78) or 0.78),
            ambiguous_gap_threshold=float(search_policy.get("ambiguous_gap_threshold", 0.08) or 0.08),
            max_return_candidates=int(search_policy.get("max_return_candidates", 5) or 5),
            enable_fulltext_verify=bool(search_policy.get("enable_fulltext_verify", True)),
            max_fulltext_candidates=int(search_policy.get("max_fulltext_candidates", 3) or 3),
        ),
    )
