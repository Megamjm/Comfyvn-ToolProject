from __future__ import annotations

"""
DeepL API adapter (dry-run).

The module exposes registry metadata, credential diagnostics, and translation
dry-run helpers so Studio tooling can exercise flows without live credentials.
"""

import os
from typing import Any, Dict, Iterable, List, Mapping

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "deepl"
DOCS_URL = "https://www.deepl.com/docs-api"
PRICING_URL = "https://www.deepl.com/pricing"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_TRANSLATE_DEEPL_KEY",
    "DEEPL_AUTH_KEY",
    "DEEPL_API_KEY",
)
SECRET_KEYS: tuple[str, ...] = ("api_key", "token", "key")
OPTIONAL_ENV: tuple[str, ...] = (
    "COMFYVN_TRANSLATE_DEEPL_ENDPOINT",
    "COMFYVN_TRANSLATE_DEEPL_FORMALITY",
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
        "name": base.get("name", "DeepL API"),
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
    _ = cfg, source, target  # placeholders until live implementation
    dry_run = not credentials_present()
    return [text if dry_run else text for text in texts]


def dry_run_payload(
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, object] | None = None,
) -> Dict[str, Any]:
    config = provider_secrets(PROVIDER_ID)
    if cfg:
        config.update(dict(cfg))
    formality = str(config.get("formality") or config.get("formality_preference") or "")
    endpoint = str(
        config.get("endpoint") or os.getenv("COMFYVN_TRANSLATE_DEEPL_ENDPOINT") or ""
    )
    messages = list(texts)
    return {
        "provider": PROVIDER_ID,
        "items": [
            {
                "src": src,
                "tgt": tgt,
                "source_lang": source or "auto",
                "target_lang": target or "EN",
                "formality": (formality or "").lower() or "default",
            }
            for src, tgt in zip(messages, translate(messages, source, target, cfg))
        ],
        "usage": {
            "characters": sum(len(t) for t in messages),
            "dry_run": True,
        },
        "dry_run": True,
        "credentials_present": credentials_present(),
        "config": {
            "endpoint": endpoint or "auto",
            "formality": formality or "default",
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
