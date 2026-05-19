from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GeneralConfig:
    default_provider_id: str = ""
    thinking_provider_id: str = ""
    debug: bool = False


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
    enable_query_rewrite: bool = True


@dataclass(frozen=True)
class PaperOSConfig:
    general: GeneralConfig
    core_api: CoreAPIConfig
    search_policy: SearchPolicyConfig


def _section(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    return value if isinstance(value, dict) else {}


def load_config(raw: Mapping[str, Any]) -> PaperOSConfig:
    """Convert AstrBotConfig/dict into typed PaperOSConfig.

    AstrBotConfig behaves like dict. Keeping conversion here prevents UI schema
    details from leaking into service/client modules.
    """
    general = _section(raw, "general")
    core_api = _section(raw, "core_api")
    search_policy = _section(raw, "search_policy")

    return PaperOSConfig(
        general=GeneralConfig(
            default_provider_id=str(general.get("default_provider_id", "") or ""),
            thinking_provider_id=str(general.get("thinking_provider_id", "") or ""),
            debug=bool(general.get("debug", False)),
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
            enable_query_rewrite=bool(search_policy.get("enable_query_rewrite", True)),
        ),
    )
