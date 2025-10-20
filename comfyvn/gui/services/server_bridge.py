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

    def __init__(self, base: Optional[str] = None):
        super().__init__()
        self.base_url = (base or DEFAULT_BASE).rstrip("/")
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 3
        self._latest: Dict[str, Any] = {}

    # ─────────────────────────────
    # Async polling loop (non-blocking)
    # ─────────────────────────────
    async def _poll_once(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as cli:
                response = await cli.get(f"{self.base_url}/system/metrics")
        except Exception as exc:
            logger.error("Metrics polling error: %s", exc, exc_info=True)
            self._latest = {"ok": False, "error": str(exc)}
            self.status_updated.emit(self._latest)
            return

        if response.status_code == 200:
            try:
                payload = response.json()
            except Exception:
                payload = {}
            self._latest = payload
            logger.debug("Received system metrics: %s", payload)
            self.status_updated.emit(payload)
        else:
            logger.warning("Metrics request failed: %s", response.status_code)
            self._latest = {"ok": False, "status": response.status_code}
            self.status_updated.emit(self._latest)

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
                if method.upper() == "POST":
                    response = cli.post(url, json=payload)
                else:
                    response = cli.get(url, params=payload)
        except Exception as exc:
            logger.error("%s %s failed: %s", method.upper(), url, exc, exc_info=True)
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

    def save_settings(self, payload: Dict[str, Any], cb: Optional[Callable[[Dict[str, Any]], None]] = None):
        return self.post_json("/settings/save", payload, cb=cb)
    def post(self, path: str, payload: Dict[str, Any], *, timeout: float = 5.0, cb: Optional[Callable[[Dict[str, Any]], None]] = None, default: Any = _UNSET):
        return self.post_json(path, payload, timeout=timeout, cb=cb, default=default)

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
        self.base_url = host.rstrip("/")
        logger.info("ServerBridge host set to %s", self.base_url)
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
