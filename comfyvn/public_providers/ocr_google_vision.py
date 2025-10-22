from __future__ import annotations

"""
Google Vision OCR adapter (dry-run).

Provides registry metadata, credential diagnostics, and mock OCR payloads for
modders who need to inspect response shapes without live credentials.
"""

import os
from typing import Any, Dict, Iterable, Mapping, Sequence

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "google_vision"
DOCS_URL = "https://cloud.google.com/vision/docs/ocr"
PRICING_URL = "https://cloud.google.com/vision/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_OCR_GOOGLE_API_KEY",
    "COMFYVN_OCR_GOOGLE_CREDENTIALS",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "credentials", "service_account")
DEFAULT_FEATURES: Sequence[str] = ("TEXT_DETECTION",)


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
        "name": base.get("name", "Google Cloud Vision"),
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


def dry_run_payload(
    *,
    features: Iterable[str] | None = None,
    language_hints: Iterable[str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    selected_features = list(features or DEFAULT_FEATURES)
    hints = list(language_hints or ())
    cfg = dict(config or {})
    cfg.setdefault("project", os.getenv("COMFYVN_OCR_GOOGLE_PROJECT", "sample-project"))
    cfg.setdefault("location", os.getenv("COMFYVN_OCR_GOOGLE_LOCATION", "us"))
    text = "Lorem ipsum — Vision OCR dry-run placeholder."
    tokens = [
        {"text": "Lorem", "confidence": 0.99},
        {"text": "ipsum", "confidence": 0.98},
    ]
    return {
        "provider": PROVIDER_ID,
        "dry_run": True,
        "credentials_present": credentials_present(),
        "features": selected_features,
        "language_hints": hints,
        "config": cfg,
        "text": text,
        "blocks": [
            {
                "text": text,
                "confidence": 0.96,
                "bounding_poly": [
                    {"x": 0, "y": 0},
                    {"x": 400, "y": 0},
                    {"x": 400, "y": 120},
                    {"x": 0, "y": 120},
                ],
                "tokens": tokens,
            }
        ],
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "dry_run_payload",
    "health",
    "registry_entry",
]
