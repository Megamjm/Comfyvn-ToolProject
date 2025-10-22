from __future__ import annotations

"""
Deepgram speech-to-text adapter (dry-run).

Exposes metadata, credential diagnostics, and transcription placeholders to
support Studio debug tooling and modder automation.
"""

import os
from typing import Any, Dict, Iterable, Mapping

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "deepgram"
DOCS_URL = "https://developers.deepgram.com/docs"
PRICING_URL = "https://deepgram.com/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_SPEECH_DEEPGRAM_KEY",
    "DEEPGRAM_API_KEY",
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
        "name": base.get("name", "Deepgram"),
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
    diarize: bool = False,
    language: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    _ = audio_source, config  # preserved for API parity
    transcript = "Deepgram dry-run transcript placeholder."
    return {
        "provider": PROVIDER_ID,
        "dry_run": True,
        "credentials_present": credentials_present(),
        "model": model or "nova-2-general",
        "language": language or "auto",
        "diarize": diarize,
        "text": transcript,
        "segments": [
            {
                "text": transcript,
                "start": 0.0,
                "end": 3.5,
                "confidence": 0.88,
            }
        ],
        "confidence": 0.9,
        "duration": 3.5,
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "health",
    "registry_entry",
    "transcribe",
]
