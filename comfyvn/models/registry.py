"""
LLM model registry loader.

The registry is a JSON document that defines provider-neutral metadata for LLM
endpoints and the models they expose.  This module wraps a small amount of
validation, applies environment overrides, and exposes helper utilities for the
API layer to discover providers and instantiate adapters.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Tuple

REGISTRY_FILENAME = "registry.json"
REGISTRY_PATH = Path(__file__).resolve().with_name(REGISTRY_FILENAME)
DEFAULT_TIMEOUT_SECONDS = 30.0


class RegistryError(RuntimeError):
    """Raised when the registry cannot be loaded."""


def _slugify(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.strip().upper())


def _coerce_tags(raw: Any) -> Tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, (list, tuple, set)):
        return tuple(sorted({str(tag).strip() for tag in raw if str(tag).strip()}))
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    return ()


def _ensure_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


@dataclass(slots=True)
class ModelEntry:
    """Metadata for an individual model within a provider."""

    id: str
    tags: Tuple[str, ...] = field(default_factory=tuple)
    label: str | None = None
    description: str | None = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderConfig:
    """Resolved provider configuration after applying environment overrides."""

    name: str
    adapter: str
    base_url: str
    models: Tuple[ModelEntry, ...] = field(default_factory=tuple)
    api_key: str | None = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    settings: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def find_model(self, model_id: str) -> ModelEntry | None:
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    @property
    def tags(self) -> Tuple[str, ...]:
        merged: set[str] = set()
        for model in self.models:
            merged.update(model.tags)
        return tuple(sorted(merged))


AdapterConfig = ProviderConfig


def _read_registry_file() -> Dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"providers": [], "defaults": {}}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - config file could be invalid
        raise RegistryError(f"Failed to load LLM registry ({REGISTRY_PATH}): {exc}")


def _parse_model_entry(raw: MutableMapping[str, Any]) -> ModelEntry | None:
    model_id = str(raw.get("id") or "").strip()
    if not model_id:
        return None
    tags = _coerce_tags(raw.get("tags"))
    label = str(raw.get("label")).strip() if raw.get("label") else None
    description = (
        str(raw.get("description")).strip() if raw.get("description") else None
    )
    options = _ensure_dict(raw.get("options") or {})
    return ModelEntry(
        id=model_id,
        tags=tags,
        label=label,
        description=description,
        options=options,
    )


def _parse_provider(raw: MutableMapping[str, Any]) -> ProviderConfig | None:
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    adapter = str(raw.get("adapter") or name).strip()
    base_url = str(raw.get("base") or raw.get("base_url") or "").strip()
    metadata = _ensure_dict(raw.get("meta") or raw.get("metadata") or {})
    headers = {
        str(key): str(value)
        for key, value in _ensure_dict(raw.get("headers") or {}).items()
        if value is not None
    }
    settings = _ensure_dict(raw.get("settings") or {})
    timeout_value = raw.get("timeout")
    timeout = float(timeout_value) if timeout_value not in (None, "") else None

    models_raw = raw.get("models")
    models: List[ModelEntry] = []
    if isinstance(models_raw, Iterable):
        for entry in models_raw:
            if isinstance(entry, MutableMapping):
                model_entry = _parse_model_entry(entry)
                if model_entry:
                    models.append(model_entry)

    provider = ProviderConfig(
        name=name,
        adapter=adapter,
        base_url=base_url,
        models=tuple(models),
        headers=headers,
        settings=settings,
        metadata=metadata,
    )

    if timeout is not None and timeout > 0:
        provider.timeout = timeout

    api_key = raw.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        provider.api_key = api_key.strip()

    return _apply_env_overrides(provider)


def _apply_env_overrides(provider: ProviderConfig) -> ProviderConfig:
    slug = _slugify(provider.name)
    base_override = os.getenv(f"COMFYVN_LLM_{slug}_BASE_URL")
    if base_override:
        provider.base_url = base_override.strip()

    key_override = os.getenv(f"COMFYVN_LLM_{slug}_API_KEY")
    if key_override:
        provider.api_key = key_override.strip()

    headers_override = os.getenv(f"COMFYVN_LLM_{slug}_HEADERS")
    if headers_override:
        try:
            parsed = json.loads(headers_override)
            if isinstance(parsed, Mapping):
                provider.headers.update({str(k): str(v) for k, v in parsed.items()})
        except json.JSONDecodeError:
            pass

    timeout_override = os.getenv(f"COMFYVN_LLM_{slug}_TIMEOUT")
    if timeout_override:
        try:
            override_value = float(timeout_override)
        except ValueError:
            override_value = provider.timeout
        if override_value > 0:
            provider.timeout = override_value

    generic_timeout = os.getenv("COMFYVN_LLM_DEFAULT_TIMEOUT")
    if generic_timeout and provider.timeout == DEFAULT_TIMEOUT_SECONDS:
        try:
            override_value = float(generic_timeout)
        except ValueError:
            override_value = DEFAULT_TIMEOUT_SECONDS
        if override_value > 0:
            provider.timeout = override_value

    return provider


@lru_cache(maxsize=1)
def get_registry() -> Dict[str, Any]:
    """Return the raw registry document."""
    data = _read_registry_file()
    providers_raw = data.get("providers")
    if not isinstance(providers_raw, Iterable):
        data["providers"] = []
    defaults = data.get("defaults")
    if not isinstance(defaults, Mapping):
        data["defaults"] = {}
    return data


def refresh_registry() -> None:
    """Clear the cached registry data."""
    get_registry.cache_clear()


def iter_providers() -> Iterator[ProviderConfig]:
    registry = get_registry()
    providers_raw = registry.get("providers", [])
    for entry in providers_raw:
        if isinstance(entry, MutableMapping):
            provider = _parse_provider(entry)
            if provider:
                yield provider


def resolve_provider(name: str) -> ProviderConfig | None:
    target = name.strip().lower()
    for provider in iter_providers():
        if provider.name.lower() == target:
            return provider
    return None


def iter_models() -> Iterator[Tuple[ProviderConfig, ModelEntry]]:
    for provider in iter_providers():
        for model in provider.models:
            yield provider, model


__all__ = [
    "AdapterConfig",
    "ModelEntry",
    "ProviderConfig",
    "RegistryError",
    "get_registry",
    "iter_models",
    "iter_providers",
    "refresh_registry",
    "resolve_provider",
]
