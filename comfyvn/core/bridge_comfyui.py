import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/modules/comfy_bridge.py
# ⚙️ 3. Server Core Production Chat — Async Job Polling Integrated [ComfyVN Architect]

import json
import threading
import time

import requests


class ComfyUIBridge:
    """Handles all communications with ComfyUI REST API, now async-capable."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url.rstrip("/")

    def _safe_request(self, endpoint: str, payload: dict = None, method: str = "POST"):
        """Safely perform REST calls and handle errors."""
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            if method.upper() == "POST":
                response = requests.post(url, json=payload, timeout=10)
            else:
                response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "mock": True}

    # -------------------------------
    # Core Job Queue
    # -------------------------------
    def queue_render(self, prompt_text: str, output_path: str = "./outputs/latest.png"):
        """Submit render job to ComfyUI queue."""
        payload = {
            "prompt": {
                "1": {
                    "inputs": {"text": prompt_text, "seed": 42},
                    "class_type": "CLIPTextEncode",
                }
            },
            "output": output_path,
        }
        return self._safe_request("prompt", payload)

    # -------------------------------
    # Polling System
    # -------------------------------
    def poll_job(self, job_id: str, timeout: int = 30, interval: int = 2):
        """Poll ComfyUI history for job completion."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            res = self._safe_request(f"history/{job_id}", method="GET")
            if "error" not in res and res.get("status") == "complete":
                return {"status": "complete", "result": res}
            time.sleep(interval)
        return {"status": "timeout", "job_id": job_id}

    def queue_and_wait(
        self,
        prompt_text: str,
        output_path: str = "./outputs/latest.png",
        wait: bool = True,
    ):
        """Combined: Queue + optional wait for result."""
        queue_res = self.queue_render(prompt_text, output_path)
        job_id = queue_res.get("job_id") or queue_res.get("id") or "mock_job"

        if not wait:
            return {"status": "queued", "job_id": job_id}

        # Polling in background thread for non-blocking operation
        result_container = {"status": "polling", "job_id": job_id}

        def _poll():
            result_container.update(self.poll_job(job_id))

        t = threading.Thread(target=_poll, daemon=True)
        t.start()
        return result_container
