from __future__ import annotations

"""
AssemblyAI speech-to-text adapter (dry-run).

Provides metadata, credential diagnostics, and mock transcripts for automation
and documentation flows.
"""

import os
from typing import Any, Dict, Iterable, Mapping

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "assemblyai"
DOCS_URL = "https://www.assemblyai.com/docs"
PRICING_URL = "https://www.assemblyai.com/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_SPEECH_ASSEMBLYAI_KEY",
    "ASSEMBLYAI_API_KEY",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "token", "key")


def _credential_snapshot() -> Dict[str, Any]:
    secrets = provider_secrets(PROVIDER_ID)
    env_hits = {key: bool(os.getenv(key)) for key in ENV_KEYS}
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
        "name": base.get("name", "AssemblyAI"),
        "docs_url": DOCS_URL,
        "pricing_url": PRICING_URL,
        "last_checked": LAST_CHECKED,
        "pricing": base.get("pricing", {}),
        "reviews": base.get("reviews", {}),
        "notes": base.get("notes", ""),
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


def transcribe(
    audio_source: bytes | str | Iterable[bytes],
    *,
    model: str | None = None,
    sentiment_analysis: bool = False,
    auto_highlights: bool = False,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    _ = audio_source, config
    transcript = "AssemblyAI dry-run transcript placeholder."
    return {
        "provider": PROVIDER_ID,
        "dry_run": True,
        "credentials_present": credentials_present(),
        "model": model or "best",
        "text": transcript,
        "segments": [
            {
                "text": transcript,
                "start": 0.0,
                "end": 4.2,
                "confidence": 0.87,
            }
        ],
        "confidence": 0.88,
        "duration": 4.2,
        "sentiment_analysis": sentiment_analysis,
        "auto_highlights": auto_highlights,
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "health",
    "registry_entry",
    "transcribe",
]
