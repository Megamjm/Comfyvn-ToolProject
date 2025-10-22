from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from fastapi import APIRouter, Body, HTTPException

from comfyvn.config import feature_flags
from comfyvn.security.sandbox import NetworkGuard
from comfyvn.security.secrets_store import SecretStoreError, default_store

router = APIRouter(prefix="/api/security", tags=["Security"])

SECURITY_FEATURE_FLAG = "enable_security_api"
SECURITY_LOG_ENV = "COMFYVN_SECURITY_LOG_FILE"
DEFAULT_SANDBOX_FLAG = "SANDBOX_NETWORK"
DEFAULT_SANDBOX_ALLOW = "SANDBOX_NETWORK_ALLOW"


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled(SECURITY_FEATURE_FLAG):
        raise HTTPException(status_code=403, detail="security api disabled")


def _security_log_path() -> Path:
    raw = os.getenv(SECURITY_LOG_ENV)
    if raw:
        return Path(raw).expanduser()
    return Path("logs/security.log")


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _current_allowlist() -> List[str]:
    raw = os.getenv(DEFAULT_SANDBOX_ALLOW, "")
    if not raw:
        return []
    entries = []
    for item in raw.split(","):
        cand = item.strip()
        if cand:
            entries.append(cand)
    return entries


def _coerce_port(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="port must be an integer") from None
    if port < 0 or port > 65535:
        raise HTTPException(status_code=400, detail="port must be between 0-65535")
    return port


@router.get("/secrets/providers")
def list_secret_providers() -> Dict[str, Any]:
    _ensure_enabled()
    store = default_store()
    providers = store.describe_all()
    return {
        "ok": True,
        "providers": providers,
        "log_path": str(_security_log_path()),
    }


@router.post("/secrets/rotate")
def rotate_secret_key(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    _ensure_enabled()
    requested = payload.get("new_key")
    new_key_value: str | None = None
    if requested is not None:
        new_key_value = str(requested).strip()
        if not new_key_value:
            raise HTTPException(status_code=400, detail="new_key must be non-empty")
    store = default_store()
    try:
        raw_key = store.rotate_key(new_key_value)
    except SecretStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    fingerprint = _fingerprint(raw_key)
    providers = store.describe_all()
    return {
        "ok": True,
        "fingerprint": fingerprint,
        "providers": providers,
        "log_path": str(_security_log_path()),
    }


@router.get("/audit")
def read_security_audit(limit: int = 50) -> Dict[str, Any]:
    _ensure_enabled()
    limit = max(1, min(int(limit), 200))
    path = _security_log_path()
    if not path.exists():
        return {"ok": True, "items": [], "log_path": str(path)}
    records: collections.deque[str] = collections.deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                records.append(line)
        modified = path.stat().st_mtime
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    parsed: List[Dict[str, Any]] = []
    for entry in records:
        try:
            parsed.append(json.loads(entry))
        except json.JSONDecodeError:
            parsed.append({"raw": entry})
    return {
        "ok": True,
        "items": parsed,
        "log_path": str(path),
        "last_modified": modified,
    }


@router.get("/sandbox/defaults")
def sandbox_defaults() -> Dict[str, Any]:
    _ensure_enabled()
    network_flag = os.getenv(DEFAULT_SANDBOX_FLAG, "0").strip().lower()
    network_enabled = network_flag in {"1", "true", "yes", "on"}
    allow = _current_allowlist()
    return {
        "ok": True,
        "network_enabled": network_enabled,
        "network_allow": allow,
    }


@router.post("/sandbox/check")
def sandbox_check(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _ensure_enabled()
    host = str(payload.get("host") or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="host is required")
    port = _coerce_port(payload.get("port"))
    allow_raw = payload.get("allow")
    if allow_raw is None:
        allow: Sequence[str] | Iterable[str] = _current_allowlist()
    elif isinstance(allow_raw, str):
        allow = [allow_raw]
    elif isinstance(allow_raw, (list, tuple, set)):
        allow = [str(item).strip() for item in allow_raw if str(item).strip()]
    else:
        raise HTTPException(status_code=400, detail="allow must be a list or string")
    guard = NetworkGuard(allow)
    allowed = guard.allowed(host, port)
    return {
        "ok": True,
        "host": host,
        "port": port,
        "allowed": allowed,
        "network_allow": list(allow),
    }
