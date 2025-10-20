from PySide6.QtGui import QAction

# comfyvn/core/gpu_monitor.py
# [Phase 0.95] Background GPU Monitor thread for local + remote endpoints

import threading, time, httpx, json, os

class GPUMonitor:
    def __init__(self, base='http://127.0.0.1:8001', interval=5):
        self.base = base
        self.interval = interval
        self.running = False
        self.data = {}
        self.thread = None

    def _loop(self):
        while self.running:
            try:
                with httpx.Client(timeout=2.5) as c:
                    local = c.get(f"{self.base}/gpu/list").json()
                    remotes = []
                    if os.path.exists("config/remote_gpus.json"):
                        rem = json.load(open("config/remote_gpus.json","r",encoding="utf-8"))
                        for e in rem.get("endpoints", []):
                            try:
                                r = c.get(f"{e['endpoint']}/gpu/list")
                                if r.status_code < 400:
                                    remotes.append({"endpoint":e["endpoint"],"gpus":r.json().get("gpus",[])})
                            except Exception:
                                pass
                    self.data = {"local": local.get("gpus", []), "remote": remotes}
            except Exception:
                self.data = {}
            time.sleep(self.interval)

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)