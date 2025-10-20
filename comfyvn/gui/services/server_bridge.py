from __future__ import annotations
# comfyvn/gui/services/server_bridge.py
# [ComfyVN Architect | Phase 2.05 | Async Bridge + Non-blocking refresh]
import asyncio
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import httpx
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class ServerBridge(QObject):
    status_updated = Signal(dict)

    def __init__(self, base: str = "http://127.0.0.1:8001"):
        super().__init__()
        self.base_url = base.rstrip("/")
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 3
        self._latest: Dict[str, Any] = {}

    # ─────────────────────────────
    # Async polling loop (non-blocking)
    # ─────────────────────────────
    async def _poll_once(self) -> None:
        async with httpx.AsyncClient(timeout=3.0) as cli:
            try:
                response = await cli.get(f"{self.base_url}/system/metrics")
                if response.status_code == 200:
                    self._latest = response.json()
                    logger.debug("Received system metrics: %s", self._latest)
                    self.status_updated.emit(self._latest)
                else:
                    logger.warning("Metrics request failed: %s", response.status_code)
            except Exception as exc:
                logger.error("Metrics polling error: %s", exc, exc_info=True)
                self._latest = {"ok": False, "error": str(exc)}
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
    def _post(self, path: str, payload: Dict[str, Any], cb: Optional[Callable[[Dict[str, Any]], None]] = None):
        url = f"{self.base_url}{path}"

        def _worker():
            result: Dict[str, Any]
            try:
                with httpx.Client(timeout=5.0) as cli:
                    response = cli.post(url, json=payload)
                result = {"ok": response.status_code < 400, "status": response.status_code}
                try:
                    result["data"] = response.json()
                except Exception:
                    result["data"] = response.text
                logger.debug("POST %s -> %s", url, result["status"])
            except Exception as exc:
                logger.error("POST %s failed: %s", url, exc, exc_info=True)
                result = {"ok": False, "error": str(exc)}
            if cb:
                cb(result)
            return result

        thread = threading.Thread(target=_worker, daemon=True, name=f"ServerBridgePOST:{path}")
        thread.start()
        return thread

    def save_settings(self, payload: Dict[str, Any], cb: Optional[Callable[[Dict[str, Any]], None]] = None):
        return self._post("/settings/save", payload, cb)

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
