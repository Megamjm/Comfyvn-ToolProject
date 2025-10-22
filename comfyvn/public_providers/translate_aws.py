from __future__ import annotations

"""
Amazon Translate adapter (dry-run).

Provides registry metadata, credential diagnostics, and mock responses so teams
can exercise routing logic without invoking the AWS API.
"""

import os
from typing import Any, Dict, Iterable, List, Mapping

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "amazon_translate"
DOCS_URL = "https://docs.aws.amazon.com/translate/latest/dg/what-is.html"
PRICING_URL = "https://aws.amazon.com/translate/pricing/"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_TRANSLATE_AWS_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)
SECRET_KEYS: tuple[str, ...] = ("access_key", "secret_key", "session_token")
OPTIONAL_ENV: tuple[str, ...] = (
    "COMFYVN_TRANSLATE_AWS_REGION",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
)


def _credential_snapshot() -> Dict[str, Any]:
    secrets = provider_secrets("amazon_translate")
    env_hits = {key: bool(os.getenv(key)) for key in (*ENV_KEYS, *OPTIONAL_ENV)}
    secret_hits = {key: bool(secrets.get(key)) for key in SECRET_KEYS}
    try:
        resolved = resolve_credential(
            "amazon_translate", env_keys=ENV_KEYS, secret_keys=SECRET_KEYS
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
    base = find_provider("amazon_translate") or {}
    entry = {
        "id": "amazon_translate",
        "name": base.get("name", "Amazon Translate"),
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
    region = (
        os.getenv("COMFYVN_TRANSLATE_AWS_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    return {
        "provider": "amazon_translate",
        "ok": snap["resolved"],
        "dry_run": True,
        "region": region,
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
    _ = cfg, source, target
    dry_run = not credentials_present()
    return [text if dry_run else text for text in texts]


def dry_run_payload(
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, object] | None = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "terminology_names": [],
        "region": (
            os.getenv("COMFYVN_TRANSLATE_AWS_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        ),
    }
    if cfg:
        params.update({k: v for k, v in dict(cfg).items() if v is not None})
    messages = list(texts)
    return {
        "provider": "amazon_translate",
        "items": [
            {
                "src": src,
                "tgt": tgt,
                "source_lang": source or "auto",
                "target_lang": target or "en",
            }
            for src, tgt in zip(messages, translate(messages, source, target, cfg))
        ],
        "usage": {
            "characters": sum(len(t) for t in messages),
            "dry_run": True,
        },
        "dry_run": True,
        "credentials_present": credentials_present(),
        "config": params,
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "dry_run_payload",
    "health",
    "registry_entry",
    "translate",
]
