from __future__ import annotations

"""
OpenAI LLM adapter (dry-run routing).

Exposes pricing metadata, credential diagnostics, and chat routing plans so the
LLM router can perform dry-runs without contacting the OpenAI API.
"""

import os
from typing import Any, Dict, Iterable, Mapping, Sequence

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "openai"
DOCS_URL = "https://platform.openai.com/docs/guides/text-generation"
PRICING_URL = "https://openai.com/api/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_LLM_OPENAI_KEY",
    "OPENAI_API_KEY",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "key", "token")
OPTIONAL_ENV: tuple[str, ...] = (
    "COMFYVN_LLM_OPENAI_ENDPOINT",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "OPENAI_ORG_ID",
)
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_CHAT_PATH = "/chat/completions"
MODEL_REGISTRY: Sequence[Dict[str, Any]] = (
    {
        "id": "gpt-4o",
        "label": "GPT-4o",
        "context": 128_000,
        "tags": ["vision", "tool_use", "general"],
        "pricing": {"input_per_million": 5.0, "output_per_million": 15.0},
    },
    {
        "id": "gpt-4o-mini",
        "label": "GPT-4o mini",
        "context": 128_000,
        "tags": ["general", "fast", "cost_optimized"],
        "pricing": {"input_per_million": 0.15, "output_per_million": 0.60},
    },
    {
        "id": "gpt-4.1-mini",
        "label": "GPT-4.1 mini",
        "context": 128_000,
        "tags": ["general", "llm_router"],
        "pricing": {"input_per_million": 0.30, "output_per_million": 1.20},
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
    base = find_provider("openai") or {}
    entry = {
        "id": PROVIDER_ID,
        "name": base.get("name", "OpenAI Platform"),
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
        os.getenv("COMFYVN_LLM_OPENAI_ENDPOINT")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or DEFAULT_BASE_URL
    ).rstrip("/")


def _select_model(model_id: str | None) -> Dict[str, Any]:
    if not model_id:
        return dict(MODEL_REGISTRY[1])  # GPT-4o mini default
    needle = model_id.lower()
    for model in MODEL_REGISTRY:
        if model["id"].lower() == needle:
            return dict(model)
    # Fallback with tags for router exploration
    fallback = dict(MODEL_REGISTRY[1])
    fallback.setdefault("aliases", []).append(model_id)
    return fallback


def plan_chat(payload: Mapping[str, Any]) -> Dict[str, Any]:
    messages = payload.get("messages") or []
    if not isinstance(messages, Iterable):
        messages = []
    model_id = payload.get("model") or payload.get("preferred_model")
    temperature = payload.get("temperature", 0.7)
    max_tokens = payload.get("max_tokens")
    tools = payload.get("tools") or ()
    model = _select_model(model_id)
    org = os.getenv("OPENAI_ORG_ID") or os.getenv("COMFYVN_LLM_OPENAI_ORG")
    headers = {
        "Authorization": "Bearer <redacted>" if credentials_present() else "<missing>",
        "Content-Type": "application/json",
    }
    if org:
        headers["OpenAI-Organization"] = org
    body: Dict[str, Any] = {
        "model": model["id"],
        "messages": list(messages),
        "temperature": temperature,
    }
    if isinstance(max_tokens, int):
        body["max_tokens"] = max_tokens
    if isinstance(tools, Iterable):
        body["tools"] = list(tools)
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
            "has_tools": bool(body.get("tools")),
        },
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "health",
    "plan_chat",
    "registry_entry",
]
