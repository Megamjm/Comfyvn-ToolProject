# comfyvn/gui/server_bridge.py
# 🌐 Server Bridge — Modular Server Communication Layer (v4.0)
# [ComfyVN_Architect | GUI <-> FastAPI Bridge]

import time, json, httpx, threading, requests
from typing import Optional


class ServerBridge:
    """Provides a stable interface between GUI and the ComfyVN backend."""

    def __init__(self, base_url: Optional[str] = None):
        self.api_base = base_url or "http://127.0.0.1:8001"
        self.online = False
        self.last_status = {}
        self.port_candidates = [8001, 8002]
        self.lock = threading.Lock()

    # ------------------------------------------------------------
    # 🔍 Connection & Health
    # ------------------------------------------------------------
    def ensure_online(self) -> bool:
        """Attempt to connect to known ports and auto-select a healthy one."""
        for port in self.port_candidates:
            url = f"http://127.0.0.1:{port}/health"
            try:
                r = requests.get(url, timeout=2)
                if r.status_code == 200:
                    self.api_base = f"http://127.0.0.1:{port}"
                    self.online = True
                    return True
            except Exception:
                continue
        self.online = False
        return False

    def get_status(self) -> dict:
        """Fetch server status or health info."""
        try:
            r = requests.get(f"{self.api_base}/status", timeout=4)
            if r.status_code != 200:
                r = requests.get(f"{self.api_base}/health", timeout=4)
            self.last_status = r.json()
            self.online = True
            return self.last_status
        except Exception as e:
            self.online = False
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------
    # 🧠 Generic API helper
    # ------------------------------------------------------------
    def request(self, method: str, path: str, **kwargs):
        """Send HTTP requests to the backend with auto-reconnect."""
        url = f"{self.api_base}/{path.lstrip('/')}"
        try:
            resp = requests.request(method.upper(), url, timeout=10, **kwargs)
            if resp.status_code == 404:
                # fallback if the route isn't ready
                time.sleep(1)
                self.ensure_online()
                url = f"{self.api_base}/{path.lstrip('/')}"
                resp = requests.request(method.upper(), url, timeout=10, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------
    # 🚀 Embedded Server Management
    # ------------------------------------------------------------
    def start_embedded_server(self):
        """Attempt to start the embedded server in a background thread."""
        with self.lock:
            if self.online:
                print("[ServerBridge] 🟢 Server already online — skip launch.")
                return
            print("[ServerBridge] 🛰 Launching embedded server on 127.0.0.1:8001 …")

            from comfyvn.server.app import launch_server_thread

            t = threading.Thread(
                target=launch_server_thread, args=("127.0.0.1", 8001), daemon=True
            )
            t.start()
            time.sleep(3)  # give the server a moment to initialize
            if not self.ensure_online():
                print("[ServerBridge] ⚠ Retry on port 8002 …")
                t = threading.Thread(
                    target=launch_server_thread, args=("127.0.0.1", 8002), daemon=True
                )
                t.start()
                time.sleep(3)
                self.ensure_online()

    # ------------------------------------------------------------
    # 🧹 Shutdown / Reset
    # ------------------------------------------------------------
    def reset(self):
        self.online = False
        self.last_status = {}
