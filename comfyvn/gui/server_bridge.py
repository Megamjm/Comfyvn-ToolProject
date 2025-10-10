# comfyvn/gui/server_bridge.py
# [⚙️ Server Core Integration Chat]
# Bridges GUI <-> FastAPI Server Core endpoints using background threads

import threading
import requests
from typing import Callable


class ServerBridge:
    """Handles communication between ComfyVN GUI and FastAPI Server Core."""

    def __init__(self, host: str = "http://127.0.0.1:8001"):
        self.host = host.rstrip("/")

    def set_host(self, host: str):
        self.host = host.rstrip("/")

    def test_connection(self, callback: Callable[[str], None]):
        """Ping root endpoint and return status text."""
        def _work():
            try:
                r = requests.get(self.host + "/")
                if r.status_code == 200:
                    callback(f"[Server] Connected: {r.json().get('status', 'OK')}")
                else:
                    callback(f"[Server] Error: {r.status_code}")
            except Exception as e:
                callback(f"[Server] Failed to connect: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def send_scene_plan(self, scene_data: dict, callback: Callable[[dict], None]):
        """POST to /scene/plan endpoint"""
        def _work():
            try:
                url = f"{self.host}/scene/plan"
                r = requests.post(url, json=scene_data, timeout=30)
                if r.status_code == 200:
                    callback(r.json())
                else:
                    callback({"error": f"HTTP {r.status_code}", "details": r.text})
            except Exception as e:
                callback({"error": str(e)})
        threading.Thread(target=_work, daemon=True).start()

    def send_render_request(self, render_data: dict, callback: Callable[[dict], None]):
        """POST to /scene/render endpoint"""
        def _work():
            try:
                url = f"{self.host}/scene/render"
                r = requests.post(url, json=render_data, timeout=60)
                callback(r.json() if r.status_code == 200 else {"error": r.text})
            except Exception as e:
                callback({"error": str(e)})
        threading.Thread(target=_work, daemon=True).start()
