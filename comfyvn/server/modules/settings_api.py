from __future__ import annotations

import copy
import logging
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException

try:
    from PySide6.QtGui import QAction  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover - optional dependency
    QAction = None  # type: ignore

from comfyvn.config.baseurl_authority import (
    current_authority,
    find_open_port,
    write_runtime_authority,
)
from comfyvn.core.settings_manager import SettingsManager

router = APIRouter(prefix="/settings", tags=["settings"])
_settings = SettingsManager()
LOGGER = logging.getLogger(__name__)
_LOCAL_HOSTS = {
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "0",
    "*",
    "::",
    "[::]",
    "::1",
}


def _merge_settings(base: dict, updates: dict) -> dict:
    """Recursively merge dictionaries, matching the launcher behaviour."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge_settings(base[key], value)
        else:
            base[key] = value
    return base


def _apply_update(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object.")
    current = _settings.load()
    merged = _merge_settings(copy.deepcopy(current), payload)
    return merged


def _connect_host(host: str) -> str:
    lowered = str(host or "").strip().lower()
    if lowered in {"0.0.0.0", "0", "*"}:
        return "127.0.0.1"
    if lowered in {"::", "[::]"}:
        return "localhost"
    return str(host or "127.0.0.1")


def _extract_endpoint(settings: dict) -> tuple[str, int, str | None]:
    authority = current_authority()
    host = authority.host or "127.0.0.1"
    port = authority.port or 8001
    base_value: str | None = None
    server_cfg = settings.get("server")
    if isinstance(server_cfg, dict):
        host_candidate = server_cfg.get("host")
        if host_candidate:
            host = str(host_candidate).strip() or host
        port_candidate = server_cfg.get("local_port")
        if port_candidate is None:
            port_candidate = server_cfg.get("port")
        try:
            if port_candidate is not None:
                port = int(port_candidate)
        except (TypeError, ValueError):
            pass
        base_value_candidate = (
            server_cfg.get("base_url")
            or server_cfg.get("endpoint")
            or server_cfg.get("url")
        )
        if isinstance(base_value_candidate, str) and base_value_candidate.strip():
            base_value = base_value_candidate.strip()
            normalized = (
                base_value
                if "://" in base_value
                else f"http://{base_value}".replace("///", "//")
            )
            parsed = urlparse(normalized)
            if parsed.hostname:
                host = parsed.hostname
            if parsed.port:
                port = parsed.port
            elif parsed.scheme == "https":
                port = 443
            elif parsed.scheme == "http":
                port = 80
    return str(host or "127.0.0.1"), int(port), base_value


def _format_base_value(original: str, host: str, port: int) -> str:
    raw = original.strip()
    if not raw:
        return raw
    if "://" not in raw:
        if "/" in raw:
            _, _, tail = raw.partition("/")
            tail = f"/{tail}" if tail else ""
            return f"{host}:{port}{tail}"
        return f"{host}:{port}"
    parsed = urlparse(raw)
    netloc = f"{host}:{port}"
    updated = parsed._replace(netloc=netloc)
    return updated.geturl()


def _apply_server_overrides(settings: dict, host: str, port: int) -> bool:
    server_cfg = settings.get("server")
    if not isinstance(server_cfg, dict):
        return False
    changed = False
    connect_host = _connect_host(host)
    if server_cfg.get("local_port") != port:
        server_cfg["local_port"] = port
        changed = True
    if "port" in server_cfg and server_cfg.get("port") != port:
        server_cfg["port"] = port
        changed = True
    if "host" in server_cfg and server_cfg.get("host") != connect_host:
        server_cfg["host"] = connect_host
        changed = True
    for key in ("base_url", "endpoint", "url"):
        value = server_cfg.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        formatted = _format_base_value(value, connect_host, port)
        if formatted != value.strip():
            server_cfg[key] = formatted
            changed = True
    return changed


def _sync_runtime_state(settings: dict) -> None:
    try:
        host, requested_port, base_hint = _extract_endpoint(settings)
        connect_host = _connect_host(host)
        lowered = host.strip().lower()
        resolved_port = requested_port
        if lowered in _LOCAL_HOSTS:
            resolved_port = find_open_port(connect_host, requested_port)
        if resolved_port != requested_port:
            LOGGER.info(
                "Server port %s unavailable on %s; selected %s.",
                requested_port,
                connect_host,
                resolved_port,
            )
        overrides_changed = _apply_server_overrides(settings, host, resolved_port)
        state_path = write_runtime_authority(connect_host, resolved_port)
        LOGGER.debug(
            "runtime_state.json updated at %s (host=%s port=%s)",
            state_path,
            host,
            resolved_port,
        )
        current_authority(refresh=True)
        scheme = "http"
        if isinstance(base_hint, str) and "://" in base_hint:
            parsed_hint = urlparse(base_hint)
            if parsed_hint.scheme:
                scheme = parsed_hint.scheme
        base_url = f"{scheme}://{connect_host}:{resolved_port}"
        os.environ["COMFYVN_SERVER_BASE"] = base_url
        os.environ["COMFYVN_BASE_URL"] = base_url
        os.environ["COMFYVN_SERVER_HOST"] = connect_host
        os.environ["COMFYVN_SERVER_PORT"] = str(resolved_port)
        if overrides_changed:
            LOGGER.info(
                "Persisted server settings now point at %s:%s",
                host,
                resolved_port,
            )
    except Exception as exc:  # pragma: no cover - defensive sync guard
        LOGGER.warning("Failed to synchronise runtime state: %s", exc)


@router.get("/get")
def get_settings():
    return _settings.load()


@router.post("/set")
def set_settings(payload: dict = Body(...)):
    merged = _apply_update(payload or {})
    _sync_runtime_state(merged)
    _settings.save(merged)
    return {"ok": True, "settings": merged, "saved": str(_settings.path)}


@router.post("/save")
def save_settings(payload: dict = Body(...)):
    merged = _apply_update(payload or {})
    _sync_runtime_state(merged)
    _settings.save(merged)
    return {"ok": True, "settings": merged, "saved": str(_settings.path)}
