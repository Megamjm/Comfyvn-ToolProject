from __future__ import annotations

# comfyvn/gui/services/server_bridge.py
# [ComfyVN Architect | Phase 2.05 | Async Bridge + Non-blocking refresh]
import asyncio
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

from comfyvn.config import feature_flags
from comfyvn.config.baseurl_authority import current_authority, default_base_url

_AUTHORITY = current_authority()
DEFAULT_BASE = (os.getenv("COMFYVN_SERVER_BASE") or _AUTHORITY.base_url).rstrip("/")
SERVER_HOST = _AUTHORITY.host
SERVER_PORT = _AUTHORITY.port


def refresh_authority_cache(*, refresh: bool = True) -> str:
    global _AUTHORITY, DEFAULT_BASE, SERVER_HOST, SERVER_PORT
    _AUTHORITY = current_authority(refresh=refresh)
    DEFAULT_BASE = (os.getenv("COMFYVN_SERVER_BASE") or _AUTHORITY.base_url).rstrip("/")
    SERVER_HOST = _AUTHORITY.host
    SERVER_PORT = _AUTHORITY.port
    return DEFAULT_BASE


_UNSET = object()


class ServerBridge(QObject):
    status_updated = Signal(dict)
    warnings_updated = Signal(list)

    def __init__(self, base: Optional[str] = None):
        super().__init__()
        self.base_url = (base or DEFAULT_BASE).rstrip("/")
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._base_interval = 2.5
        self._backoff_schedule: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0)
        self._backoff_step = 0
        self._current_interval = self._base_interval
        self._poll_lock = threading.Lock()
        self._wake_event = threading.Event()
        self._latest: Dict[str, Any] = {}
        self._warnings: list[Dict[str, Any]] = []
        self._seen_warning_ids: set[str] = set()
        self._health_debug_enabled = feature_flags.is_enabled(
            "debug_health_checks", default=False
        )
        self._last_status_ok = True
        self._last_failure_detail: str | None = None

    # ─────────────────────────────
    # Async polling loop (non-blocking)
    # ─────────────────────────────
    async def _poll_once(self) -> None:
        if not self._poll_lock.acquire(blocking=False):
            logger.debug("Polling skipped: previous request still in flight")
            return
        try:
            debug_enabled = feature_flags.is_enabled(
                "debug_health_checks", default=False
            )
            self._health_debug_enabled = debug_enabled

            async with httpx.AsyncClient(timeout=3.0) as cli:
                metrics_payload, metrics_ok = await self._fetch_metrics(cli)
                overall_ok = bool(metrics_payload.get("ok"))
                combined: Dict[str, Any] = dict(metrics_payload)

                health_payload: Optional[Dict[str, Any]] = None
                if not metrics_ok or not overall_ok or debug_enabled:
                    health_payload = await self._fetch_health(cli)
                    if health_payload is not None:
                        combined["health"] = health_payload
                        if not overall_ok:
                            overall_ok = bool(health_payload.get("ok"))

                if health_payload is None:
                    combined["health"] = {
                        "ok": overall_ok,
                        "status": 200 if overall_ok else 503,
                        "data": {"status": "Healthy" if overall_ok else "Unavailable"},
                        "source": "cached",
                    }

                combined["ok"] = overall_ok

                if metrics_ok:
                    self._backoff_step = 0
                    self._current_interval = self._base_interval
                else:
                    if self._backoff_step < len(self._backoff_schedule) - 1:
                        self._backoff_step += 1
                    self._current_interval = self._backoff_schedule[self._backoff_step]

                combined["retry_in"] = self._current_interval
                combined["state"] = "online" if overall_ok else "waiting"
                combined["poll_interval"] = self._current_interval
                combined["backoff_step"] = self._backoff_step
                combined["actions"] = self._build_actions(overall_ok)
                combined["timestamp"] = time.time()

                self._latest = combined
                self._log_status_change(
                    overall_ok, combined, debug_enabled=debug_enabled
                )
                self.status_updated.emit(dict(combined))

                if metrics_ok and overall_ok:
                    await self._process_warnings(cli)
        except Exception as exc:
            logger.error("Metrics polling error: %s", exc, exc_info=True)
            if self._backoff_step < len(self._backoff_schedule) - 1:
                self._backoff_step += 1
            self._current_interval = self._backoff_schedule[self._backoff_step]
            self._latest = {
                "ok": False,
                "error": str(exc),
                "state": "waiting",
                "retry_in": self._current_interval,
                "backoff_step": self._backoff_step,
                "actions": self._build_actions(False),
                "timestamp": time.time(),
            }
            self._log_status_change(False, self._latest, debug_enabled=False)
            self.status_updated.emit(dict(self._latest))
        finally:
            self._poll_lock.release()

    async def _fetch_metrics(
        self, client: httpx.AsyncClient
    ) -> tuple[Dict[str, Any], bool]:
        try:
            response = await client.get(f"{self.base_url}/system/metrics")
        except Exception as exc:
            logger.warning("Metrics request failed: %s", exc)
            payload: Dict[str, Any] = {"ok": False, "error": str(exc)}
            return payload, False
        return await self._process_metrics_response(response)

    async def _process_metrics_response(
        self, response: httpx.Response
    ) -> tuple[Dict[str, Any], bool]:
        if response.status_code == 200:
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {"ok": True, "data": payload}
            payload.setdefault("ok", True)
            logger.debug("Received system metrics: %s", payload)
            return payload, True

        logger.warning("Metrics request failed: %s", response.status_code)
        payload = {"ok": False, "status": response.status_code}
        return payload, False

    async def _fetch_health(
        self, client: httpx.AsyncClient
    ) -> Optional[Dict[str, Any]]:
        try:
            response = await client.get(f"{self.base_url}/health")
        except Exception as exc:
            logger.debug("Health request failed: %s", exc)
            return {"ok": False, "error": str(exc)}

        payload: Dict[str, Any]
        try:
            data = response.json()
        except Exception:
            data = {}

        ok = response.status_code < 400
        if isinstance(data, dict):
            data_ok = data.get("ok")
            if data_ok is not None:
                ok = bool(data_ok)
            elif str(data.get("status")).lower() in {"ok", "healthy"}:
                ok = True

        payload = {
            "ok": ok,
            "status": response.status_code,
            "data": data if isinstance(data, dict) else {"raw": data},
        }
        return payload

    async def _process_warnings(self, client: httpx.AsyncClient) -> None:
        try:
            warn_resp = await client.get(
                f"{self.base_url}/api/system/warnings", params={"limit": 20}
            )
        except Exception as exc:
            logger.debug("Warning fetch failed: %s", exc)
            return

        if warn_resp.status_code != 200:
            return

        try:
            warn_payload = warn_resp.json()
        except Exception:
            warn_payload = {}
        warnings = (
            warn_payload.get("warnings", []) if isinstance(warn_payload, dict) else []
        )
        if not isinstance(warnings, list):
            return
        new_warnings = []
        for item in warnings:
            if not isinstance(item, dict):
                continue
            warn_id = str(item.get("id") or "")
            if warn_id and warn_id in self._seen_warning_ids:
                continue
            if warn_id:
                self._seen_warning_ids.add(warn_id)
            new_warnings.append(item)
        if new_warnings:
            self._warnings.extend(new_warnings)
            self._warnings = self._warnings[-50:]
            self.warnings_updated.emit(new_warnings)

    def _log_status_change(
        self, ok: bool, payload: Dict[str, Any], *, debug_enabled: bool
    ) -> None:
        if debug_enabled:
            logger.debug("Metrics poll -> %s", payload)
            self._last_status_ok = ok
            if not ok:
                detail = self._compose_failure_message(payload)
                if detail:
                    self._last_failure_detail = detail
            return

        if ok:
            if not self._last_status_ok:
                logger.info("Metrics/health recovered")
            self._last_failure_detail = None
        else:
            detail = self._compose_failure_message(payload)
            if detail != self._last_failure_detail:
                logger.warning("Metrics degraded: %s", detail or "unknown issue")
                self._last_failure_detail = detail
        self._last_status_ok = ok

    @staticmethod
    def _compose_failure_message(payload: Dict[str, Any]) -> str | None:
        if not isinstance(payload, dict):
            return None
        detail: Any = payload.get("error")
        status_code: Any = payload.get("status")
        health = payload.get("health")
        if isinstance(health, dict):
            status_code = health.get("status") or status_code
            detail = detail or health.get("error")
            data = health.get("data")
            if isinstance(data, dict):
                detail = detail or data.get("error") or data.get("detail")
            elif isinstance(data, str) and not detail:
                detail = data
        data_payload = payload.get("data")
        if not detail and isinstance(data_payload, dict):
            detail = data_payload.get("error") or data_payload.get("detail")

        message_parts = []
        if detail:
            message_parts.append(str(detail))
        if status_code:
            message_parts.append(f"HTTP {status_code}")
        if not message_parts:
            return None
        return " — ".join(message_parts)

    def start_polling(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop = False
            self._wake_event.set()
            return
        self._stop = False
        self._wake_event.clear()

        def _loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while not self._stop:
                loop.run_until_complete(self._poll_once())
                if self._stop:
                    break
                wait_for = self._current_interval
                if wait_for <= 0:
                    continue
                triggered = self._wake_event.wait(timeout=wait_for)
                self._wake_event.clear()
                if triggered:
                    continue

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="ServerBridgePoller"
        )
        self._thread.start()
        logger.info("ServerBridge polling started for %s", self.base_url)

    def stop_polling(self) -> None:
        self._stop = True
        self._wake_event.set()
        thread = self._thread
        if thread and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=0.5)
        self._thread = None
        logger.info("ServerBridge polling stopped")

    # ─────────────────────────────
    # REST helpers
    # ─────────────────────────────
    def _build_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _request_sync(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        url = self._build_url(path)
        result: Dict[str, Any] = {"ok": False, "status": None, "data": None}
        try:
            with httpx.Client(timeout=timeout) as cli:
                method_upper = method.upper()
                if method_upper in {"POST", "PUT", "PATCH", "DELETE"}:
                    response = cli.request(
                        method_upper, url, json=payload if payload else None
                    )
                else:
                    response = cli.get(url, params=payload)
        except Exception as exc:
            logger.warning("%s %s failed: %s", method.upper(), url, exc)
            result.update({"error": str(exc)})
            return result

        result["status"] = response.status_code
        result["ok"] = response.status_code < 400
        try:
            result["data"] = response.json()
        except Exception:
            result["data"] = response.text
        logger.debug("%s %s -> %s", method.upper(), url, response.status_code)
        return result

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: float = 5.0,
        cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        def worker():
            result = self._request_sync(method, path, payload, timeout=timeout)
            if cb:
                try:
                    cb(result)
                except Exception:
                    logger.exception("ServerBridge callback failed")
            return result

        if cb:
            thread = threading.Thread(
                target=worker, daemon=True, name=f"ServerBridge{method.upper()}:{path}"
            )
            thread.start()
            return thread
        return worker()

    def get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout: float = 3.0,
        cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        default: Any = _UNSET,
    ):
        result = self._request("GET", path, params, timeout=timeout, cb=cb)
        if cb:
            return result
        if isinstance(result, dict) and result.get("ok"):
            return result
        if default is not _UNSET:
            return default
        return result

    def post_json(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        timeout: float = 5.0,
        cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        default: Any = _UNSET,
    ):
        result = self._request("POST", path, payload, timeout=timeout, cb=cb)
        if cb:
            return result
        if isinstance(result, dict) and result.get("ok"):
            return result
        if default is not _UNSET:
            return default
        return result

    def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        if not isinstance(payload, dict):
            payload = {}
        return self.post_json(path, payload, cb=callback)

    def save_settings(self, payload: dict, callback=None):
        return self._post("/settings/save", payload, callback)

    def post(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        timeout: float = 5.0,
        cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        default: Any = _UNSET,
    ):
        return self.post_json(path, payload, timeout=timeout, cb=cb, default=default)

    def providers_list(self) -> Optional[Dict[str, Any]]:
        result = self.get_json("/api/providers/list", default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_create(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result = self.post_json("/api/providers/create", payload, default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_register(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result = self.post_json("/api/providers/register", payload, default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data

    def get_warnings(self) -> list[Dict[str, Any]]:
        return list(self._warnings)

    def latest(self) -> Dict[str, Any]:
        return dict(self._latest)

    def retry_delay(self) -> float:
        if self._latest.get("ok"):
            return 0.0
        return max(self._current_interval, 0.0)

    def _build_actions(self, success: bool) -> list[Dict[str, str]]:
        if success:
            return []
        return [{"label": "Reconnect now", "command": "reconnect"}]

    def reconnect(self) -> None:
        self._backoff_step = 0
        self._current_interval = 0.0
        self._stop = False
        self.start_polling()
        self._wake_event.set()
        snapshot: Dict[str, Any] = dict(self._latest) if self._latest else {}
        snapshot.update(
            {
                "ok": False,
                "state": "waiting",
                "retry_in": 0.0,
                "actions": self._build_actions(False),
                "backoff_step": 0,
            }
        )
        self.status_updated.emit(snapshot)

    def providers_activate(
        self, provider_id: str, active: bool
    ) -> Optional[Dict[str, Any]]:
        result = self.post_json(
            "/api/providers/activate",
            {"id": provider_id, "active": active},
            default=None,
        )
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_reorder(self, order: list[str]) -> Optional[Dict[str, Any]]:
        result = self.post_json("/api/providers/order", {"order": order}, default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_remove(self, provider_id: str) -> Optional[Dict[str, Any]]:
        result = self._request(
            "DELETE", f"/api/providers/remove/{provider_id}", timeout=5.0
        )
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_export(
        self, include_secrets: bool = False
    ) -> Optional[Dict[str, Any]]:
        params = {"include_secrets": "true" if include_secrets else "false"}
        result = self.get_json("/api/providers/export", params, default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_import(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result = self.post_json("/api/providers/import", payload, default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_health(
        self, provider_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        payload = {"id": provider_id} if provider_id else None
        result = self.post_json("/api/providers/health", payload or {}, default=None)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def ping(self, timeout: float = 0.5) -> bool:
        result = self.get_json("/system/ping", timeout=timeout)
        if not result.get("ok"):
            return False
        data = result.get("data") or {}
        if isinstance(data, dict):
            return bool(data.get("ok", True))
        return True

    def ensure_online(self, *, autostart: bool = True, deadline: float = 12.0) -> bool:
        autostart_env = os.getenv("COMFYVN_SERVER_AUTOSTART", "1").lower()
        if autostart_env in {"0", "false", "no"}:
            autostart = False
        if not autostart or not self._is_local_base():
            return self.ping()
        try:
            from comfyvn.gui.server_boot import wait_for_server
        except Exception as exc:
            logger.warning("wait_for_server unavailable: %s", exc)
            return self.ping()
        ok = wait_for_server(self.base_url, autostart=True, deadline=deadline)
        if ok:
            new_base = refresh_authority_cache(refresh=True)
            if self._is_local_base():
                self.base_url = new_base
        return ok

    def projects(self) -> list[Dict[str, Any]]:
        result = self.get_json("/projects/list")
        if not result.get("ok"):
            return []
        data = result.get("data") or {}
        if isinstance(data, dict):
            return data.get("items", [])
        return []

    def projects_create(self, name: str) -> Dict[str, Any]:
        payload = {"name": name}
        return self.post_json("/projects/create", payload)

    def projects_select(self, name: str) -> Dict[str, Any]:
        return self.post_json(f"/projects/select/{name}", {})

    def set_host(self, host: str):
        self.base_url = host
        return self.base_url

    @property
    def base(self) -> str:
        return self.base_url

    @base.setter
    def base(self, value: str) -> None:
        self.set_host(value)

    def get(self, path: str, default=None):
        try:
            return self._latest.get(path, default)
        except Exception:
            return default

    def set(self, key: str, value: Any) -> Any:
        self._latest[key] = value
        return value

    def _is_local_base(self) -> bool:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
