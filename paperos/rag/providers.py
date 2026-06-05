from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedEmbeddingProvider:
    provider: Any
    provider_id: str
    name: str
    dim: int


async def resolve_embedding_provider(context: Any, provider_id: str = "") -> ResolvedEmbeddingProvider:
    """Resolve an AstrBot embedding provider without implementing one locally."""

    getter = getattr(context, "get_all_embedding_providers", None)
    if getter is None:
        raise EmbeddingProviderError(
            "AstrBot context does not expose get_all_embedding_providers(); "
            "please run PaperOS inside an AstrBot runtime with embedding providers configured."
        )

    raw_providers = await _maybe_await(getter())
    providers = _normalize_provider_collection(raw_providers)
    if not providers:
        raise EmbeddingProviderError("No AstrBot embedding provider is configured.")

    selected = _select_provider(providers, provider_id.strip())
    dim_getter = getattr(selected.provider, "get_dim", None)
    if dim_getter is None:
        raise EmbeddingProviderError(
            f"Embedding provider {selected.label!r} does not expose get_dim()."
        )
    dim = int(await _maybe_await(dim_getter()))
    if dim <= 0:
        raise EmbeddingProviderError(
            f"Embedding provider {selected.label!r} returned invalid dimension: {dim!r}."
        )
    return ResolvedEmbeddingProvider(
        provider=selected.provider,
        provider_id=selected.provider_id,
        name=selected.name,
        dim=dim,
    )


async def get_embeddings(provider: Any, texts: list[str]) -> list[list[float]]:
    method = getattr(provider, "get_embeddings", None)
    if method is None:
        raise EmbeddingProviderError("Resolved embedding provider does not expose get_embeddings(texts).")
    raw = await _maybe_await(method(texts))
    vectors = _normalize_vectors(raw)
    if len(vectors) != len(texts):
        raise EmbeddingProviderError(
            f"Embedding provider returned {len(vectors)} vectors for {len(texts)} texts."
        )
    return vectors


async def get_embeddings_batched(
    provider: Any,
    texts: list[str],
    *,
    batch_size: int = 16,
) -> list[list[float]]:
    """Use AstrBot's batch helper when available, otherwise batch get_embeddings()."""

    if not texts:
        return []

    batch_size = max(1, int(batch_size))
    batch_method = getattr(provider, "get_embeddings_batch", None)
    if batch_method is not None:
        raw = await _maybe_await(batch_method(texts, batch_size=batch_size))
        vectors = _normalize_vectors(raw)
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                f"Embedding provider returned {len(vectors)} vectors for {len(texts)} texts."
            )
        return vectors

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(await get_embeddings(provider, texts[start : start + batch_size]))
    return vectors


@dataclass(frozen=True)
class _ProviderCandidate:
    provider: Any
    provider_id: str
    name: str

    @property
    def label(self) -> str:
        return self.name or self.provider_id or self.provider.__class__.__name__


def _normalize_provider_collection(raw: Any) -> list[_ProviderCandidate]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        items = raw.items()
    else:
        items = enumerate(raw)

    candidates: list[_ProviderCandidate] = []
    for key, value in items:
        provider = value
        config = getattr(provider, "provider_config", None)
        config = config if isinstance(config, dict) else {}
        provider_id = str(
            getattr(provider, "id", "")
            or getattr(provider, "provider_id", "")
            or getattr(provider, "provider_name", "")
            or config.get("id", "")
            or config.get("provider_id", "")
            or config.get("name", "")
            or key
            or ""
        )
        name = str(
            getattr(provider, "name", "")
            or getattr(provider, "provider_name", "")
            or getattr(provider, "model_name", "")
            or config.get("name", "")
            or config.get("model", "")
            or config.get("provider", "")
            or ""
        )
        candidates.append(_ProviderCandidate(provider=provider, provider_id=provider_id, name=name))
    return candidates


def _select_provider(candidates: list[_ProviderCandidate], provider_id: str) -> _ProviderCandidate:
    if provider_id:
        lowered = provider_id.casefold()
        for candidate in candidates:
            if lowered in {
                candidate.provider_id.casefold(),
                candidate.name.casefold(),
                candidate.label.casefold(),
            }:
                return candidate
        available = ", ".join(candidate.label for candidate in candidates)
        raise EmbeddingProviderError(
            f"Embedding provider {provider_id!r} was not found. Available providers: {available}."
        )
    if len(candidates) == 1:
        return candidates[0]
    available = ", ".join(candidate.label for candidate in candidates)
    raise EmbeddingProviderError(
        "Multiple AstrBot embedding providers are configured; set rag.embedding_provider_id. "
        f"Available providers: {available}."
    )


def _normalize_vectors(raw: Any) -> list[list[float]]:
    if isinstance(raw, dict):
        for key in ("embeddings", "vectors", "data"):
            if key in raw:
                raw = raw[key]
                break
    vectors: list[list[float]] = []
    for item in raw or []:
        vector = item.get("embedding") if isinstance(item, dict) and "embedding" in item else item
        vectors.append([float(value) for value in vector])
    return vectors


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
