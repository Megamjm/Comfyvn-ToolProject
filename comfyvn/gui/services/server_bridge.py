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

DEFAULT_BASE = os.getenv("COMFYVN_SERVER_BASE", "http://127.0.0.1:8001")
_UNSET = object()


class ServerBridge(QObject):
    status_updated = Signal(dict)
    warnings_updated = Signal(list)

    def __init__(self, base: Optional[str] = None):
        super().__init__()
        self.base_url = (base or DEFAULT_BASE).rstrip("/")
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 3
        self._latest: Dict[str, Any] = {}
        self._warnings: list[Dict[str, Any]] = []
        self._seen_warning_ids: set[str] = set()

    # ─────────────────────────────
    # Async polling loop (non-blocking)
    # ─────────────────────────────
    async def _poll_once(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as cli:
                metrics_payload, metrics_ok = await self._fetch_metrics(cli)
                health_payload = await self._fetch_health(cli)

                combined: Dict[str, Any] = dict(metrics_payload)
                overall_ok = bool(metrics_payload.get("ok"))
                if health_payload is not None:
                    combined["health"] = health_payload
                    if not overall_ok:
                        overall_ok = bool(health_payload.get("ok"))
                combined["ok"] = overall_ok

                self._latest = combined
                logger.debug("Metrics poll -> %s", combined)
                self.status_updated.emit(dict(combined))

                if metrics_ok:
                    await self._process_warnings(cli)
        except Exception as exc:
            logger.error("Metrics polling error: %s", exc, exc_info=True)
            self._latest = {"ok": False, "error": str(exc)}
            self.status_updated.emit(self._latest)

    async def _fetch_metrics(self, client: httpx.AsyncClient) -> tuple[Dict[str, Any], bool]:
        try:
            response = await client.get(f"{self.base_url}/system/metrics")
        except Exception as exc:
            logger.warning("Metrics request failed: %s", exc)
            payload: Dict[str, Any] = {"ok": False, "error": str(exc)}
            return payload, False
        return await self._process_metrics_response(response)

    async def _process_metrics_response(self, response: httpx.Response) -> tuple[Dict[str, Any], bool]:
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

    async def _fetch_health(self, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
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
            warn_resp = await client.get(f"{self.base_url}/api/system/warnings", params={"limit": 20})
        except Exception as exc:
            logger.debug("Warning fetch failed: %s", exc)
            return

        if warn_resp.status_code != 200:
            return

        try:
            warn_payload = warn_resp.json()
        except Exception:
            warn_payload = {}
        warnings = warn_payload.get("warnings", []) if isinstance(warn_payload, dict) else []
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

    def start_polling(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False

        def _loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while not self._stop:
                loop.run_until_complete(self._poll_once())
                time.sleep(self._interval)

        self._thread = threading.Thread(target=_loop, daemon=True, name="ServerBridgePoller")
        self._thread.start()
        logger.info("ServerBridge polling started for %s", self.base_url)

    def stop_polling(self) -> None:
        self._stop = True
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
                    response = cli.request(method_upper, url, json=payload if payload else None)
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
            thread = threading.Thread(target=worker, daemon=True, name=f"ServerBridge{method.upper()}:{path}")
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

    def save_settings(
        self,
        payload: Dict[str, Any],
        cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        *,
        timeout: float = 8.0,
    ):
        if not isinstance(payload, dict):
            logger.warning("save_settings expects dict payload, received %s", type(payload).__name__)
            payload = {}
        return self.post_json("/settings/save", payload, timeout=timeout, cb=cb)

    def post(self, path: str, payload: Dict[str, Any], *, timeout: float = 5.0, cb: Optional[Callable[[Dict[str, Any]], None]] = None, default: Any = _UNSET):
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

    def providers_activate(self, provider_id: str, active: bool) -> Optional[Dict[str, Any]]:
        result = self.post_json("/api/providers/activate", {"id": provider_id, "active": active}, default=None)
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
        result = self._request("DELETE", f"/api/providers/remove/{provider_id}", timeout=5.0)
        if not isinstance(result, dict):
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return None

    def providers_export(self, include_secrets: bool = False) -> Optional[Dict[str, Any]]:
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

    def providers_health(self, provider_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        return wait_for_server(self.base_url, autostart=True, deadline=deadline)

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

    def set_host(self, host: str) -> str:
        if not host:
            return self.base_url
        candidate = host.strip()
        if not candidate:
            return self.base_url
        if "://" not in candidate:
            candidate = f"http://{candidate}"
        parsed = urlparse(candidate)
        if not parsed.scheme or not parsed.netloc:
            logger.warning("Invalid host supplied to ServerBridge.set_host: %s", host)
            return self.base_url
        normalized = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.path and parsed.path != "/":
            normalized += parsed.path.rstrip("/")
        normalized = normalized.rstrip("/")
        if normalized == self.base_url:
            return self.base_url

        logger.info("ServerBridge host updating from %s to %s", self.base_url, normalized)
        self.base_url = normalized
        self._latest = {}
        self._warnings.clear()
        self._seen_warning_ids.clear()

        was_polling = self._thread is not None and self._thread.is_alive()
        if was_polling:
            self.stop_polling()
            self.start_polling()
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
