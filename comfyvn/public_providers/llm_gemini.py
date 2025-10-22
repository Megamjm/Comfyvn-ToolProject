from __future__ import annotations

"""
Google Gemini adapter (dry-run routing).
"""

import os
from typing import Any, Dict, Iterable, Mapping, Sequence

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "google_gemini"
DOCS_URL = "https://ai.google.dev/gemini-api/docs"
PRICING_URL = "https://ai.google.dev/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_LLM_GEMINI_KEY",
    "GOOGLE_API_KEY",
    "GENAI_API_KEY",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "key", "token")
OPTIONAL_ENV: tuple[str, ...] = (
    "COMFYVN_LLM_GEMINI_ENDPOINT",
    "GOOGLE_GEMINI_ENDPOINT",
)
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL_REGISTRY: Sequence[Dict[str, Any]] = (
    {
        "id": "gemini-2.0-flash",
        "label": "Gemini 2.0 Flash",
        "context": 1_000_000,
        "tags": ["multimodal", "fast", "cost_optimized"],
        "pricing": {"input_per_million": 0.10, "output_per_million": 0.40},
    },
    {
        "id": "gemini-2.0-pro",
        "label": "Gemini 2.0 Pro",
        "context": 2_000_000,
        "tags": ["reasoning", "enterprise"],
        "pricing": {"input_per_million": 3.50, "output_per_million": 10.50},
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
        "name": base.get("name", "Google Gemini"),
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
        os.getenv("COMFYVN_LLM_GEMINI_ENDPOINT")
        or os.getenv("GOOGLE_GEMINI_ENDPOINT")
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
    safety_settings = payload.get("safety") or ()
    generation_config = payload.get("generation_config") or {}
    tools = payload.get("tools") or ()
    model = _select_model(model_id)
    base_url = _base_url()
    url = f"{base_url}/models/{model['id']}:generateContent"
    headers = {
        "x-goog-api-key": "<redacted>" if credentials_present() else "<missing>",
        "content-type": "application/json",
    }
    body: Dict[str, Any] = {
        "contents": list(messages),
    }
    if generation_config:
        body["generationConfig"] = dict(generation_config)
    if isinstance(safety_settings, Iterable):
        body["safetySettings"] = list(safety_settings)
    if isinstance(tools, Iterable):
        body["tools"] = list(tools)
    return {
        "provider": PROVIDER_ID,
        "dry_run": True,
        "credentials_present": credentials_present(),
        "endpoint": url,
        "dispatch": {
            "method": "POST",
            "url": url,
            "headers": headers,
            "json": body,
        },
        "model": model["id"],
        "model_info": model,
        "inputs": {
            "message_count": len(body["contents"]),
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
