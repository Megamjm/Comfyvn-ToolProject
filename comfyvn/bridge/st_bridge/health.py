"""SillyTavern bridge health probes."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from comfyvn.config import feature_flags
from comfyvn.core.settings_manager import SettingsManager

try:  # pragma: no cover - optional dependency may be missing in headless envs
    from comfyvn.integrations.sillytavern_bridge import (
        SillyTavernBridge,
        SillyTavernBridgeError,
    )
except Exception:  # pragma: no cover - fall back when PySide/httpx not present
    SillyTavernBridge = None  # type: ignore

    class SillyTavernBridgeError(RuntimeError):
        """Fallback error when SillyTavern bridge helper is unavailable."""


from .extension_sync import (
    ExtensionPathInfo,
    collect_extension_status,
    resolve_paths,
)

LOGGER = logging.getLogger(__name__)


def _ping(url: str, *, timeout: float) -> dict[str, object]:
    """Perform a lightweight GET request and capture timing/result details."""
    start = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout)
        latency = (time.perf_counter() - start) * 1000.0
        info: dict[str, object] = {
            "ok": response.ok,
            "status_code": response.status_code,
            "latency_ms": round(latency, 2),
            "url": url,
        }
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                info["json"] = response.json()
            except ValueError:
                info["text"] = response.text[:200]
        else:
            snippet = response.text.strip()
            if snippet:
                info["text"] = snippet[:200]
        return info
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000.0
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": round(latency, 2),
            "url": url,
        }


def _build_base_from_host(
    host: Optional[str], port: Optional[int | str]
) -> Optional[str]:
    if not host:
        return None
    raw = str(host).strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or parsed.path or ""
    if not hostname:
        return None
    effective_port: Optional[int]
    if parsed.port:
        effective_port = parsed.port
    else:
        try:
            effective_port = int(port) if port else None
        except (TypeError, ValueError):
            effective_port = None
    netloc = hostname
    if effective_port:
        netloc = f"{hostname}:{effective_port}"
    return f"{scheme}://{netloc}".rstrip("/")


def _load_bridge(
    *,
    settings: Optional[SettingsManager],
    base_url: Optional[str],
    plugin_base: Optional[str],
    timeout: float,
) -> tuple[Optional[SillyTavernBridge], dict[str, object]]:
    """
    Instantiate the SillyTavern bridge helper, capturing configuration details.
    """
    bridge: Optional[SillyTavernBridge] = None
    config_view: dict[str, object] = {}
    if SillyTavernBridge is None:
        return (
            None,
            {
                "base_url": (base_url or "").rstrip("/"),
                "plugin_base": plugin_base,
                "token_present": False,
                "error": "SillyTavern bridge helper unavailable",
            },
        )
    try:
        bridge = SillyTavernBridge(
            base_url=base_url,
            plugin_base=plugin_base,
            settings=settings,
            timeout=timeout,
        )
        config_view = {
            "base_url": bridge.base_url,
            "plugin_base": bridge.plugin_base,
            "token_present": bool(bridge.token),
            "user_id": bridge.user_id,
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.debug("Failed to initialise SillyTavern bridge helper: %s", exc)
        config_view = {
            "base_url": (base_url or "").rstrip("/"),
            "plugin_base": plugin_base,
            "token_present": False,
            "error": str(exc),
        }
    return bridge, config_view


def _merge_config(
    path_info: ExtensionPathInfo,
    bridge_config: dict[str, object],
) -> dict[str, object]:
    """Combine configuration snapshots from resolve_paths and the bridge helper."""
    merged = dict(path_info.config)
    merged.setdefault("enabled", path_info.enabled)
    for key, value in bridge_config.items():
        if key == "token_present":
            merged["token_present"] = bool(value)
            continue
        if value is None:
            continue
        merged[key] = value
    return merged


def probe_health(
    *,
    settings: Optional[SettingsManager] = None,
    base_url: Optional[str] = None,
    plugin_base: Optional[str] = None,
    timeout: float = 3.0,
) -> dict[str, object]:
    """
    Probe SillyTavern availability and plugin health.

    Returns a dictionary with the ping result, plugin health payload (if
    available), resolved path information, and a summary status that callers can
    surface in diagnostics panels.
    """
    try:
        settings_manager = settings or SettingsManager()
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.debug("Failed to load settings manager: %s", exc)
        settings_manager = None

    paths = resolve_paths(settings=settings_manager)
    if not feature_flags.is_enabled("enable_sillytavern_bridge"):
        return {
            "status": "disabled",
            "enabled": False,
            "base_url": None,
            "plugin_base": None,
            "ping": None,
            "plugin": None,
            "paths": paths.as_dict(),
            "config": {
                "enabled": False,
                "message": "SillyTavern bridge disabled via feature flag.",
            },
            "extension": None,
            "versions": {"extension": {}, "plugin": {}},
            "alerts": ["feature_disabled"],
        }
    config_base_hint = paths.config.get("base_url") or paths.config.get("base") or None
    host_hint = paths.config.get("host")
    port_hint = paths.config.get("port")
    computed_base = config_base_hint or _build_base_from_host(host_hint, port_hint)
    config_plugin_hint = paths.config.get("plugin_base")

    bridge, bridge_config = _load_bridge(
        settings=settings_manager,
        base_url=base_url or (str(computed_base) if computed_base else None),
        plugin_base=plugin_base
        or (str(config_plugin_hint) if config_plugin_hint else None),
        timeout=timeout,
    )

    effective_base = bridge.base_url if bridge else bridge_config.get("base_url", "")
    if not effective_base and computed_base:
        effective_base = str(computed_base)
    ping_result: dict[str, object] | None = None

    if effective_base:
        ping_url = f"{effective_base.rstrip('/')}/ping"
        ping_result = _ping(ping_url, timeout=timeout)
    else:
        ping_result = {
            "ok": False,
            "error": "base_url unavailable",
        }

    plugin_health: dict[str, Any] | None = None
    plugin_status = "unknown"
    if bridge:
        try:
            plugin_health = bridge.health()
            plugin_status = str(plugin_health.get("status", "ok"))
        except SillyTavernBridgeError as exc:
            plugin_health = {"ok": False, "error": str(exc)}
            plugin_status = "error"
        finally:
            bridge.close()
    elif bridge_config.get("error"):
        plugin_health = {"ok": False, "error": bridge_config["error"]}
        plugin_status = "error"

    overall_status = "disabled" if not paths.enabled else "offline"
    if paths.enabled:
        if ping_result.get("ok"):
            overall_status = "ok"
        elif plugin_health and plugin_health.get("ok"):
            # Plugin responded but the main ping failed.
            overall_status = "degraded"
        elif plugin_status == "ok":
            overall_status = "degraded"

    merged_config = _merge_config(paths, bridge_config)
    extension_state = collect_extension_status(paths=paths)
    extension_version_status = str(extension_state.get("version_status", "unknown"))
    plugin_info = extension_state.get("plugin", {}) or {}
    plugin_version_status = str(
        extension_state.get(
            "plugin_version_status", plugin_info.get("version_status", "unknown")
        )
    )
    bundle_plugin_version = (
        plugin_info.get("source", {}).get("package", {}).get("version")
    )
    installed_plugin_version = (
        (plugin_info.get("destination_package") or {}).get("version")
        if plugin_info
        else None
    )
    extension_versions = {
        "source": extension_state.get("source_manifest", {}).get("version"),
        "installed": extension_state.get("dest_manifest", {}).get("version"),
        "status": extension_version_status,
    }
    plugin_versions = {
        "bundled": bundle_plugin_version,
        "installed": installed_plugin_version,
        "remote": plugin_health.get("version") if plugin_health else None,
        "status": plugin_version_status,
    }

    alerts: list[str] = []
    if extension_version_status in {"mismatch", "missing"}:
        alerts.append(f"extension_{extension_version_status}")
    if plugin_version_status in {"mismatch", "missing"}:
        alerts.append(f"plugin_{plugin_version_status}")
    if plugin_health and not plugin_health.get("ok", True):
        alerts.append("plugin_health_error")

    if overall_status == "ok":
        if extension_version_status in {
            "mismatch",
            "missing",
        } or plugin_version_status in {
            "mismatch",
            "missing",
        }:
            overall_status = "degraded"
    if (
        plugin_health
        and not plugin_health.get("ok", True)
        and overall_status not in {"disabled", "error"}
    ):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "enabled": paths.enabled,
        "base_url": effective_base,
        "plugin_base": merged_config.get("plugin_base"),
        "ping": ping_result,
        "plugin": plugin_health,
        "paths": paths.as_dict(),
        "config": merged_config,
        "extension": extension_state,
        "versions": {
            "extension": extension_versions,
            "plugin": plugin_versions,
        },
        "alerts": alerts,
    }
