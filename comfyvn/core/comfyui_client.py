from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

LOGGER = logging.getLogger("comfyvn.comfyui.client")


class ComfyUIClient:
    """Lightweight HTTP helper for interacting with ComfyUI's REST endpoints."""

    def __init__(
        self,
        base: str = "http://127.0.0.1:8188",
        *,
        session: Optional[requests.Session] = None,
    ):
        self.base = base.rstrip("/")
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    # Health / utilities
    # ------------------------------------------------------------------
    def health(self, timeout: float = 0.5) -> bool:
        url = f"{self.base}/system_stats"
        try:
            response = self.session.get(url, timeout=timeout)
            return response.ok
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Prompt execution
    # ------------------------------------------------------------------
    def queue_prompt(
        self, workflow: Dict[str, Any], *, timeout: float = 20.0
    ) -> Dict[str, Any]:
        url = f"{self.base}/prompt"
        response = self.session.post(url, json=workflow, timeout=timeout)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            LOGGER.debug(
                "ComfyUI prompt response was not JSON: %s", response.text[:256]
            )
            return {"prompt_id": None, "raw": response.text}

    def get_history(self, prompt_id: str, *, timeout: float = 10.0) -> Dict[str, Any]:
        url = f"{self.base}/history/{prompt_id}"
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            LOGGER.debug(
                "ComfyUI history response was not JSON: %s", response.text[:256]
            )
            return {}

    def wait_for_history(
        self,
        prompt_id: str,
        *,
        timeout: float = 120.0,
        poll_interval: float = 1.5,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = self.get_history(prompt_id)
            if history:
                return history
            time.sleep(poll_interval)
        raise TimeoutError(f"Timeout fetching history for prompt {prompt_id}")


__all__ = ["ComfyUIClient"]
