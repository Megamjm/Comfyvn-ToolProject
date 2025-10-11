# comfyvn/modules/system_monitor.py
# 🧠 ComfyVN System Monitor — Phase 3.3-H
# Collects system telemetry and connection states.
# [🎨 GUI Code Production Chat]

import os, psutil, time, threading, requests, subprocess, json

try:
    import torch
except ImportError:
    torch = None


class SystemMonitor:
    """Background monitor for ServerCore, LM Studio, SillyTavern, and hardware."""

    def __init__(self, api_base="http://127.0.0.1:8001"):
        self.api_base = api_base.rstrip("/")
        self.callbacks = []
        self._running = False
        self.interval = 5
        self.data = {}

        # Default targets
        self.targets = {
            "server": f"{self.api_base}/system/metrics",
            "lmstudio": "http://127.0.0.1:1234/healthz",
            "sillytavern": "http://127.0.0.1:8000/ping",
            "world": "http://127.0.0.1:8002/world/status",
        }

    # ------------------------------------------------------------------
    def start(self, interval: int = 5):
        if not self._running:
            self._running = True
            self.interval = interval
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def on_update(self, func):
        """Register callback executed on every update."""
        if func not in self.callbacks:
            self.callbacks.append(func)

    # ------------------------------------------------------------------
    def _loop(self):
        while self._running:
            try:
                metrics = self._collect_all()
                self.data = metrics
                for cb in self.callbacks:
                    try:
                        cb(metrics)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(self.interval)

    # ------------------------------------------------------------------
    def _collect_all(self):
        info = {
            "server": self._check_server(),
            "lmstudio": self._check_lmstudio(),
            "sillytavern": self._check_sillytavern(),
            "world": self._check_world(),
        }
        sysinfo = self._collect_system_metrics()
        info.update(sysinfo)
        return info

    # ------------------------------------------------------------------
    # External Targets
    # ------------------------------------------------------------------
    def _check_server(self):
        try:
            r = requests.get(self.targets["server"], timeout=3)
            if r.status_code == 200:
                data = r.json()
                return {"state": "online", "metrics": data}
            else:
                return {"state": "warn"}
        except Exception:
            return {"state": "offline"}

    def _check_lmstudio(self):
        try:
            r = requests.get(self.targets["lmstudio"], timeout=2)
            if r.status_code == 200:
                js = r.json()
                model = js.get("model", "unknown")
                return {"state": "online", "model": model}
        except Exception:
            pass
        return {"state": "offline"}

    def _check_sillytavern(self):
        try:
            r = requests.get(self.targets["sillytavern"], timeout=2)
            if r.status_code == 200:
                js = r.json()
                if js.get("status") == "ok":
                    return {"state": "online"}
        except Exception:
            pass
        return {"state": "offline"}

    def _check_world(self):
        try:
            r = requests.get(self.targets["world"], timeout=2)
            if r.status_code == 200:
                js = r.json()
                state = js.get("status", "online")
                return {"state": state}
        except Exception:
            pass
        return {"state": "offline"}

    # ------------------------------------------------------------------
    # Local System Info
    # ------------------------------------------------------------------
    def _collect_system_metrics(self):
        result = {
            "cpu_percent": psutil.cpu_percent(),
            "ram_percent": psutil.virtual_memory().percent,
            "gpu_percent": self._gpu_usage(),
        }
        return result

    def _gpu_usage(self):
        """Try torch, fallback to nvidia-smi CLI."""
        try:
            if torch and torch.cuda.is_available():
                return torch.cuda.utilization(0)
        except Exception:
            pass
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if out:
                return int(out.split("\n")[0])
        except Exception:
            pass
        return 0
