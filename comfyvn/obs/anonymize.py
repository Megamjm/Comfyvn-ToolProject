"""
Privacy-preserving helpers for telemetry and diagnostics.

This module centralises identifier hashing and anonymous installation ids so
that telemetry consumers can rely on consistent digests without exposing
raw identifiers or other personally identifiable data.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
from hashlib import blake2s
from pathlib import Path
from typing import Any, Mapping

from comfyvn.config.runtime_paths import config_dir

_STATE_LOCK = threading.Lock()
_STATE_CACHE: dict[str, Any] | None = None

_HASH_KEYWORDS = (
    "id",
    "uuid",
    "token",
    "key",
    "secret",
    "serial",
    "license",
    "path",
    "email",
    "user",
    "account",
    "identifier",
    "address",
    "fingerprint",
)


def _state_path() -> Path:
    return config_dir("telemetry", "anonymizer.json")


def _load_state() -> dict[str, Any]:
    global _STATE_CACHE
    with _STATE_LOCK:
        if _STATE_CACHE is not None:
            return dict(_STATE_CACHE)

        path = _state_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "secret" in raw:
                _STATE_CACHE = dict(raw)
                return dict(_STATE_CACHE)
        except FileNotFoundError:
            pass
        except Exception:
            # Corrupt state should be replaced with a fresh secret.
            pass

        secret = secrets.token_bytes(32)
        encoded = base64.b64encode(secret).decode("ascii")
        state = {
            "secret": encoded,
        }
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        _STATE_CACHE = dict(state)
        return dict(state)


def _secret() -> bytes:
    state = _load_state()
    raw = state.get("secret")
    if isinstance(raw, str):
        try:
            decoded = base64.b64decode(raw.encode("ascii"))
            if decoded:
                return decoded
        except Exception:
            pass
    # Fallback to regenerating a secret if decoding fails.
    secret = secrets.token_bytes(32)
    encoded = base64.b64encode(secret).decode("ascii")
    state.update({"secret": encoded})
    path = _state_path()
    with _STATE_LOCK:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        _STATE_CACHE = dict(state)
    return secret


def hash_identifier(value: str | bytes, namespace: str | None = None) -> str:
    """
    Return a stable anonymised digest for the supplied value.

    The digest is keyed by a per-installation secret so it remains consistent
    locally while still being safe to surface in telemetry payloads.
    """

    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = bytes(value)

    hasher = blake2s(key=_secret(), digest_size=16)
    if namespace:
        hasher.update(namespace.encode("utf-8"))
    hasher.update(data)
    return hasher.hexdigest()


def _should_hash(key: str) -> bool:
    key_lower = key.lower()
    return any(token in key_lower for token in _HASH_KEYWORDS)


def _anonymize_value(key: str, value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(sub_key): _anonymize_value(f"{key}.{sub_key}", sub_value)
            for sub_key, sub_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_anonymize_value(key, item) for item in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return hash_identifier(value, namespace=key)
    text = str(value)
    if _should_hash(key):
        return hash_identifier(text, namespace=key)
    if len(text) > 256:
        return text[:256] + "…"
    return text


def anonymize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively anonymise a payload mapping."""
    return {
        str(key): _anonymize_value(str(key), value) for key, value in payload.items()
    }


def anonymous_installation_id(namespace: str | None = None) -> str:
    """
    Return a deterministic anonymous identifier for the current installation.
    """

    return hash_identifier(
        "comfyvn.installation", namespace=namespace or "installation"
    )


__all__ = [
    "anonymize_payload",
    "anonymous_installation_id",
    "hash_identifier",
]
