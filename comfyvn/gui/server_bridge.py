# comfyvn/gui/server_bridge.py
# [🎨 GUI Code Production Chat | Phase 3.2 Server Sync]
# Bridges GUI <-> FastAPI Server Core endpoints using background threads

import threading
import requests
from typing import Callable, Optional


class ServerBridge:
    """Handles communication between ComfyVN GUI and FastAPI Server Core."""

    def __init__(self, host: str = "http://127.0.0.1:8001"):
        self.host = host.rstrip("/")
        self._timeout = 60

    # -------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------
    def set_host(self, host: str):
        self.host = host.rstrip("/")

    def _threaded(self, func, *args, **kwargs):
        """Run a request in a background thread."""
        threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True).start()

    # -------------------------------------------------------------
    # Core API Calls
    # -------------------------------------------------------------
    def test_connection(self, callback: Callable[[str], None]):
        """Ping root endpoint and return status text."""
        def _work():
            try:
                r = requests.get(self.host + "/", timeout=self._timeout)
                if r.status_code == 200:
                    callback(f"[Server] Connected: {r.json().get('status', 'OK')}")
                else:
                    callback(f"[Server] Error: {r.status_code}")
            except Exception as e:
                callback(f"[Server] Failed to connect: {e}")
        self._threaded(_work)

    def get_status(self, callback: Callable[[dict], None]):
        """GET /status — current mode and readiness."""
        def _work():
            try:
                r = requests.get(self.host + "/status", timeout=self._timeout)
                callback(r.json() if r.status_code == 200 else {"error": r.text})
            except Exception as e:
                callback({"error": str(e)})
        self._threaded(_work)

    def send_scene_plan(self, scene_data: dict, callback: Callable[[dict], None]):
        """POST /scene/plan endpoint."""
        def _work():
            try:
                url = f"{self.host}/scene/plan"
                r = requests.post(url, json=scene_data, timeout=self._timeout)
                if r.status_code == 200:
                    callback(r.json())
                else:
                    callback({"error": f"HTTP {r.status_code}", "details": r.text})
            except Exception as e:
                callback({"error": str(e)})
        self._threaded(_work)

    def send_render_request(self, render_data: dict, callback: Callable[[dict], None]):
        """POST /scene/render endpoint."""
        def _work():
            try:
                url = f"{self.host}/scene/render"
                r = requests.post(url, json=render_data, timeout=self._timeout)
                callback(r.json() if r.status_code == 200 else {"error": r.text})
            except Exception as e:
                callback({"error": str(e)})
        self._threaded(_work)

    def get_jobs(self, callback: Callable[[dict], None], limit: Optional[int] = None):
        """GET /jobs/poll — fetch current job queue."""
        def _work():
            try:
                url = f"{self.host}/jobs/poll"
                if limit:
                    url += f"?limit={limit}"
                r = requests.get(url, timeout=self._timeout)
                callback(r.json() if r.status_code == 200 else {"error": r.text})
            except Exception as e:
                callback({"error": str(e)})
        self._threaded(_work)

    def cancel_job(self, job_id: str, callback: Callable[[dict], None]):
        """POST /jobs/cancel — cancel job by ID."""
        def _work():
            try:
                url = f"{self.host}/jobs/cancel"
                r = requests.post(url, json={"job_id": job_id}, timeout=self._timeout)
                callback(r.json() if r.status_code == 200 else {"error": r.text})
            except Exception as e:
                callback({"error": str(e)})
        self._threaded(_work)
