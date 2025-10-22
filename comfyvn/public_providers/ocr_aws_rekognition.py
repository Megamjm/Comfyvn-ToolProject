from __future__ import annotations

"""
AWS Rekognition OCR adapter (dry-run).

Provides registry metadata, credential diagnostics, and mock detections so UI
layers can validate integrations without contacting AWS.
"""

import os
from typing import Any, Dict, Iterable, Mapping

from . import provider_secrets, resolve_credential
from .catalog import find_provider

PROVIDER_ID = "aws_rekognition"
DOCS_URL = "https://docs.aws.amazon.com/rekognition/latest/dg/text-detection.html"
PRICING_URL = "https://aws.amazon.com/rekognition/pricing/"
LAST_CHECKED = "2025-01-20"
ENV_KEYS: tuple[str, ...] = (
    "COMFYVN_OCR_AWS_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)
SECRET_KEYS: tuple[str, ...] = ("access_key", "secret_key", "session_token")
OPTIONAL_ENV: tuple[str, ...] = (
    "COMFYVN_OCR_AWS_REGION",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
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
        "name": base.get("name", "AWS Rekognition"),
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
        os.getenv("COMFYVN_OCR_AWS_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    return {
        "provider": PROVIDER_ID,
        "ok": snap["resolved"],
        "dry_run": True,
        "region": region,
        "credentials": snap,
        "pricing_url": entry["pricing_url"],
        "docs_url": entry["docs_url"],
        "last_checked": entry["last_checked"],
    }


def dry_run_payload(
    *,
    image_bytes: bytes | None = None,
    s3_object: Mapping[str, Any] | None = None,
    min_confidence: float = 0.75,
    features: Iterable[str] | None = None,
) -> Dict[str, Any]:
    _ = image_bytes, features  # parameters kept for API parity
    bucket_ref = dict(s3_object or {})
    region = (
        os.getenv("COMFYVN_OCR_AWS_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    detections = [
        {
            "text": "Rekognition dry-run placeholder",
            "confidence": 0.93,
            "bounding_box": {
                "width": 0.8,
                "height": 0.1,
                "left": 0.1,
                "top": 0.2,
            },
        }
    ]
    return {
        "provider": PROVIDER_ID,
        "dry_run": True,
        "credentials_present": credentials_present(),
        "region": region,
        "min_confidence": min_confidence,
        "s3_object": bucket_ref,
        "detections": detections,
        "credentials": _credential_snapshot(),
    }


__all__ = [
    "credentials_present",
    "dry_run_payload",
    "health",
    "registry_entry",
]
