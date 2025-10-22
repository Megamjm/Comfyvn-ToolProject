from __future__ import annotations

"""
Anthropic Claude adapter (dry-run routing).
"""

import os
from typing import Any, Dict, Iterable, Mapping, Sequence

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "anthropic"
DOCS_URL = "https://docs.anthropic.com/en/api/messages-intro"
PRICING_URL = "https://www.anthropic.com/api#pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_LLM_ANTHROPIC_KEY",
    "ANTHROPIC_API_KEY",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "key", "token")
OPTIONAL_ENV: tuple[str, ...] = ("ANTHROPIC_API_URL", "COMFYVN_LLM_ANTHROPIC_ENDPOINT")
DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_CHAT_PATH = "/messages"

MODEL_REGISTRY: Sequence[Dict[str, Any]] = (
    {
        "id": "claude-3-5-sonnet-20241022",
        "label": "Claude 3.5 Sonnet",
        "context": 200_000,
        "tags": ["reasoning", "tool_use"],
        "pricing": {"input_per_million": 3.0, "output_per_million": 15.0},
    },
    {
        "id": "claude-3-5-haiku-20241022",
        "label": "Claude 3.5 Haiku",
        "context": 200_000,
        "tags": ["fast", "cost_optimized"],
        "pricing": {"input_per_million": 1.0, "output_per_million": 5.0},
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
        "name": base.get("name", "Anthropic Claude"),
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
        os.getenv("COMFYVN_LLM_ANTHROPIC_ENDPOINT")
        or os.getenv("ANTHROPIC_API_URL")
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
    max_tokens = payload.get("max_tokens")
    temperature = payload.get("temperature", 0.7)
    system_prompt = payload.get("system") or payload.get("system_prompt")
    tools = payload.get("tools") or ()
    model = _select_model(model_id)
    headers = {
        "x-api-key": "<redacted>" if credentials_present() else "<missing>",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: Dict[str, Any] = {
        "model": model["id"],
        "messages": list(messages),
        "temperature": temperature,
    }
    if isinstance(system_prompt, str) and system_prompt.strip():
        body["system"] = system_prompt
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
