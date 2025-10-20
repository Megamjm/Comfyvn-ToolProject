from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List

import httpx

from comfyvn.core.compute_registry import get_provider_registry

LOGGER = logging.getLogger(__name__)


class GPUMonitor:
    """Background monitor polling local and remote GPU endpoints."""

    def __init__(self, base: str = "http://127.0.0.1:8001", interval: float = 5.0):
        self.base = base.rstrip("/")
        self.interval = float(interval)
        self.running = False
        self.data: Dict[str, Any] = {}
        self.thread: threading.Thread | None = None
        self.registry = get_provider_registry()

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=2.5) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            LOGGER.debug("GPU monitor failed request %s: %s", url, exc)
            return {}

    def _poll_once(self) -> Dict[str, Any]:
        local = self._fetch_json(f"{self.base}/api/gpu/list")
        remotes: List[Dict[str, Any]] = []
        for endpoint in self.registry.remote_endpoints():
            endpoint = endpoint.rstrip("/")
            data = self._fetch_json(f"{endpoint}/api/gpu/list")
            remotes.append({"endpoint": endpoint, "payload": data})
        return {"local": local, "remote": remotes}

    def _loop(self) -> None:
        while self.running:
            self.data = self._poll_once()
            time.sleep(self.interval)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
