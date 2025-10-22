from __future__ import annotations

"""
Google Translate adapter stub.

When API credentials are missing we simply echo the input so toolchains can
exercise data flows without invoking the external service.
"""

import os
from typing import Any, Dict, Iterable, List, Mapping

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "google_translate"
DOCS_URL = "https://cloud.google.com/translate/docs"
PRICING_URL = "https://cloud.google.com/translate/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_TRANSLATE_GOOGLE_API_KEY",
    "COMFYVN_TRANSLATE_GOOGLE_CREDENTIALS",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "credentials", "service_account")


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
    snap = _credential_snapshot()
    return bool(snap["resolved"])


def registry_entry() -> Dict[str, Any]:
    base = find_provider(PROVIDER_ID) or {}
    entry = {
        "id": PROVIDER_ID,
        "name": base.get("name", "Google Cloud Translation"),
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


def translate(
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, object] | None = None,
) -> List[str]:
    """
    Return translated strings.  Without credentials this is a dry-run that
    echoes the original texts.
    """

    config: Dict[str, Any] = {}
    config.update(provider_secrets(PROVIDER_ID))
    if cfg:
        config.update(dict(cfg))
    dry_run = not credentials_present()
    return [text if dry_run else text for text in texts]


def dry_run_payload(
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, object] | None = None,
) -> Dict[str, Any]:
    messages = list(texts)
    translations = translate(messages, source, target, cfg)
    config = provider_secrets(PROVIDER_ID)
    if cfg:
        for key, value in dict(cfg).items():
            if key not in config:
                config[key] = value
    return {
        "provider": PROVIDER_ID,
        "items": [
            {
                "src": src,
                "tgt": tgt,
                "source_lang": source or "auto",
                "target_lang": target or "en",
            }
            for src, tgt in zip(messages, translations)
        ],
        "usage": {
            "characters": sum(len(t) for t in messages),
            "dry_run": True,
        },
        "dry_run": True,
        "credentials_present": credentials_present(),
        "config": {
            key: ("<redacted>" if value else "") for key, value in config.items()
        },
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "dry_run_payload",
    "health",
    "registry_entry",
    "translate",
]
