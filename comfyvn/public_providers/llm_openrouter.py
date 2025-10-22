from __future__ import annotations

"""
OpenRouter adapter (dry-run routing).
"""

import os
from typing import Any, Dict, Iterable, Mapping, Sequence

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "openrouter"
DOCS_URL = "https://openrouter.ai/docs"
PRICING_URL = "https://openrouter.ai/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_LLM_OPENROUTER_KEY",
    "OPENROUTER_API_KEY",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "token", "key")
OPTIONAL_ENV: tuple[str, ...] = (
    "COMFYVN_LLM_OPENROUTER_ENDPOINT",
    "OPENROUTER_BASE_URL",
)
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_CHAT_PATH = "/chat/completions"
MODEL_REGISTRY: Sequence[Dict[str, Any]] = (
    {
        "id": "openrouter/google/gemma-2-9b-it",
        "label": "Gemma 2 9B IT (via OpenRouter)",
        "context": 8192,
        "tags": ["general", "cost_optimized"],
        "pricing": {"input_per_million": 0.10, "output_per_million": 0.10},
    },
    {
        "id": "openrouter/anthropic/claude-3.5-sonnet",
        "label": "Claude 3.5 Sonnet (via OpenRouter)",
        "context": 200_000,
        "tags": ["reasoning", "tool_use"],
        "pricing": {"input_per_million": 3.3, "output_per_million": 15.3},
    },
    {
        "id": "openrouter/openai/gpt-4.1-mini",
        "label": "GPT-4.1 mini (via OpenRouter)",
        "context": 128_000,
        "tags": ["general", "router"],
        "pricing": {"input_per_million": 0.45, "output_per_million": 1.80},
    },
)


def _credential_snapshot() -> Dict[str, Any]:
    secrets = provider_secrets(PROVIDER_ID)
    env_hits = {key: bool(os.getenv(key)) for key in (*ENV_KEYS, *OPTIONAL_ENV)}
    secret_hits = {key: bool(secrets.get(key)) for key in SECRET_KEYS}
    try:
        resolved = resolve_credential(
            PROVIDER_ID, env_keys=ENV_KEYS, secret_keys=SECRET_KEYS
        )
    except Exception:
        resolved = ""
    return {
        "env": env_hits,
        "secrets": secret_hits,
        "resolved": bool(resolved.strip()),
    }


def credentials_present() -> bool:
    return _credential_snapshot()["resolved"]


def registry_entry() -> Dict[str, Any]:
    base = find_provider(PROVIDER_ID) or {}
    entry = {
        "id": PROVIDER_ID,
        "name": base.get("name", "OpenRouter"),
        "docs_url": DOCS_URL,
        "pricing_url": PRICING_URL,
        "last_checked": LAST_CHECKED,
        "pricing": base.get("pricing", {}),
        "reviews": base.get("reviews", {}),
        "notes": base.get("notes", ""),
        "models": [dict(model) for model in MODEL_REGISTRY],
    }
    entry["pricing"]["last_checked"] = LAST_CHECKED
    entry["pricing"]["dry_run"] = True
    return entry


def health() -> Dict[str, Any]:
    snap = _credential_snapshot()
    entry = registry_entry()
    return {
        "provider": PROVIDER_ID,
        "ok": snap["resolved"],
        "dry_run": True,
        "credentials": snap,
        "pricing_url": entry["pricing_url"],
        "docs_url": entry["docs_url"],
        "last_checked": entry["last_checked"],
    }


def _base_url() -> str:
    return (
        os.getenv("COMFYVN_LLM_OPENROUTER_ENDPOINT")
        or os.getenv("OPENROUTER_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")


def _select_model(model_id: str | None) -> Dict[str, Any]:
    if not model_id:
        return dict(MODEL_REGISTRY[0])
    needle = model_id.lower()
    for model in MODEL_REGISTRY:
        if model["id"].lower() == needle:
            return dict(model)
    fallback = dict(MODEL_REGISTRY[0])
    fallback.setdefault("aliases", []).append(model_id)
    return fallback


def plan_chat(payload: Mapping[str, Any]) -> Dict[str, Any]:
    messages = payload.get("messages") or []
    if not isinstance(messages, Iterable):
        messages = []
    model_id = payload.get("model")
    route = payload.get("route")
    metadata = payload.get("metadata") or {}
    model = _select_model(model_id or route)
    headers = {
        "Authorization": "Bearer <redacted>" if credentials_present() else "<missing>",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "model": model["id"],
        "messages": list(messages),
    }
    if metadata:
        body["metadata"] = dict(metadata)
    tips = payload.get("tips")
    if isinstance(tips, (int, float)):
        body["tips"] = float(tips)
    return {
        "provider": PROVIDER_ID,
        "dry_run": True,
        "credentials_present": credentials_present(),
        "endpoint": f"{_base_url()}{DEFAULT_CHAT_PATH}",
        "dispatch": {
            "method": "POST",
            "url": f"{_base_url()}{DEFAULT_CHAT_PATH}",
            "headers": headers,
            "json": body,
        },
        "model": model["id"],
        "model_info": model,
        "inputs": {
            "message_count": len(body["messages"]),
            "metadata_keys": sorted(body.get("metadata", {}).keys()),
        },
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "health",
    "plan_chat",
    "registry_entry",
]
