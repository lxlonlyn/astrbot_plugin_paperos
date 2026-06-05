from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .storage.config import StorageConfig, load_storage_config


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
    max_hypotheses: int = 6
    max_web_search_queries: int = 5


@dataclass(frozen=True)
class CrawlerConfig:
    """On-demand URL/identifier crawler configuration.

    This is not a web-search backend. The crawler only follows concrete
    sources produced by QueryAnalyzer, such as arXiv IDs, DOI landing URLs,
    OpenReview URLs, ACL Anthology URLs, and direct PDF URLs.
    """

    enabled: bool = True
    timeout_seconds: int = 25
    max_known_urls: int = 12
    max_site_lookup_results: int = 5
    max_html_bytes: int = 2 * 1024 * 1024
    max_pdf_links_per_page: int = 8
    user_agent: str = (
        "Mozilla/5.0 (compatible; PaperOS/0.2; "
        "+https://github.com/lxlonlyn/astrbot_plugin_paperos)"
    )


@dataclass(frozen=True)
class CoreAPIConfig:
    """Legacy compatibility only.

    CORE/OpenAlex/S2-style academic APIs are intentionally outside the search
    main path. Keep this config object only so old files do not break during
    incremental migration.
    """

    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://api.core.ac.uk/v3"
    timeout_seconds: int = 25
    default_limit: int = 10
    topic_candidate_limit: int = 20
    sort: str = "relevance"


@dataclass(frozen=True)
class SearchPolicyConfig:
    accept_min_score: float = 0.70
    ambiguous_gap_threshold: float = 0.08
    identifier_title_min_similarity: float = 0.78
    max_return_candidates: int = 5
    enable_fulltext_verify: bool = True
    max_fulltext_candidates: int = 5
    download_timeout_seconds: int = 60
    max_pdf_size_mb: int = 100


@dataclass(frozen=True)
class RagConfig:
    embedding_provider_id: str = ""
    embedding_batch_size: int = 16
    vector_table_name: str = "chunk_embeddings"


@dataclass(frozen=True)
class PaperOSConfig:
    general: GeneralConfig
    query_analyzer: QueryAnalyzerConfig
    crawler: CrawlerConfig
    search_policy: SearchPolicyConfig
    core_api: CoreAPIConfig
    storage: StorageConfig
    rag: RagConfig


def _section(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    return value if isinstance(value, dict) else {}


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _int(
    value: Any,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        out = int(value)
    except Exception:
        out = default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


def _float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        out = float(value)
    except Exception:
        out = default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


def load_config(raw: Mapping[str, Any]) -> PaperOSConfig:
    """Convert AstrBotConfig/dict into typed PaperOSConfig."""

    general = _section(raw, "general")
    query_analyzer = _section(raw, "query_analyzer")
    crawler = _section(raw, "crawler")
    core_api = _section(raw, "core_api")
    search_policy = _section(raw, "search_policy")
    rag = _section(raw, "rag")

    return PaperOSConfig(
        general=GeneralConfig(
            default_provider_id=str(general.get("default_provider_id", "") or ""),
            thinking_provider_id=str(general.get("thinking_provider_id", "") or ""),
            debug=_bool(general.get("debug"), False),
        ),
        query_analyzer=QueryAnalyzerConfig(
            enabled=_bool(query_analyzer.get("enabled"), True),
            provider_id=str(query_analyzer.get("provider_id", "") or ""),
            max_repair_rounds=_int(
                query_analyzer.get("max_repair_rounds"), 1, minimum=0, maximum=3
            ),
            max_hypotheses=_int(
                query_analyzer.get("max_hypotheses"), 6, minimum=1, maximum=12
            ),
            max_web_search_queries=_int(
                query_analyzer.get("max_web_search_queries"), 5, minimum=0, maximum=5
            ),
        ),
        crawler=CrawlerConfig(
            enabled=_bool(crawler.get("enabled"), True),
            timeout_seconds=_int(
                crawler.get("timeout_seconds"), 25, minimum=3, maximum=120
            ),
            max_known_urls=_int(crawler.get("max_known_urls"), 12, minimum=1, maximum=50),
            max_site_lookup_results=_int(
                crawler.get("max_site_lookup_results"), 5, minimum=1, maximum=10
            ),
            max_html_bytes=_int(
                crawler.get("max_html_bytes"),
                2 * 1024 * 1024,
                minimum=64 * 1024,
                maximum=20 * 1024 * 1024,
            ),
            max_pdf_links_per_page=_int(
                crawler.get("max_pdf_links_per_page"), 8, minimum=1, maximum=50
            ),
            user_agent=str(crawler.get("user_agent", CrawlerConfig.user_agent) or CrawlerConfig.user_agent),
        ),
        # Legacy section. Defaults to disabled even if omitted.
        core_api=CoreAPIConfig(
            enabled=_bool(core_api.get("enabled"), False),
            api_key=str(core_api.get("api_key", "") or ""),
            base_url=str(
                core_api.get("base_url", "https://api.core.ac.uk/v3")
                or "https://api.core.ac.uk/v3"
            ).rstrip("/"),
            timeout_seconds=_int(core_api.get("timeout_seconds"), 25, minimum=3, maximum=120),
            default_limit=_int(core_api.get("default_limit"), 10, minimum=1, maximum=100),
            topic_candidate_limit=_int(
                core_api.get("topic_candidate_limit"), 20, minimum=1, maximum=100
            ),
            sort=str(core_api.get("sort", "relevance") or "relevance"),
        ),
        storage=load_storage_config(raw),
        rag=RagConfig(
            embedding_provider_id=str(rag.get("embedding_provider_id", "") or ""),
            embedding_batch_size=_int(rag.get("embedding_batch_size"), 16, minimum=1, maximum=128),
            vector_table_name=str(rag.get("vector_table_name", "chunk_embeddings") or "chunk_embeddings"),
        ),
        search_policy=SearchPolicyConfig(
            accept_min_score=_float(
                search_policy.get("accept_min_score"), 0.70, minimum=0.0, maximum=1.0
            ),
            ambiguous_gap_threshold=_float(
                search_policy.get("ambiguous_gap_threshold"), 0.08, minimum=0.0, maximum=1.0
            ),
            identifier_title_min_similarity=_float(
                search_policy.get("identifier_title_min_similarity"), 0.78, minimum=0.0, maximum=1.0
            ),
            max_return_candidates=_int(
                search_policy.get("max_return_candidates"), 5, minimum=1, maximum=20
            ),
            enable_fulltext_verify=_bool(search_policy.get("enable_fulltext_verify"), True),
            max_fulltext_candidates=_int(
                search_policy.get("max_fulltext_candidates"), 5, minimum=1, maximum=20
            ),
            download_timeout_seconds=_int(
                search_policy.get("download_timeout_seconds"), 60, minimum=5, maximum=600
            ),
            max_pdf_size_mb=_int(
                search_policy.get("max_pdf_size_mb"), 100, minimum=1, maximum=2048
            ),
        ),
    )
