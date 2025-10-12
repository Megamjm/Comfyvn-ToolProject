# comfyvn/modules/system_monitor.py
# 🧠 ComfyVN System Monitor — v2.0 (Phase 3.4-A)
# Unified telemetry collector for ServerCore, LM Studio, SillyTavern, WorldUI, and local hardware
# [🎨 GUI Code Production Chat]

import os, psutil, time, threading, requests, subprocess, json
from datetime import datetime

try:
    import torch
except ImportError:
    torch = None


class SystemMonitor:
    """Collects connection states + system hardware metrics and broadcasts to listeners."""

    def __init__(self, api_base="http://127.0.0.1:8001", debug=False):
        self.api_base = api_base.rstrip("/")
        self.debug = debug
        self.callbacks = []
        self._running = False
        self.interval = 5
        self.data = {}

        self.targets = {
            "server": f"{self.api_base}/system/metrics",
            "lmstudio": "http://127.0.0.1:1234/healthz",
            "sillytavern": "http://127.0.0.1:8000/ping",
            "world": "http://127.0.0.1:8002/world/status",
        }

    # ------------------------------------------------------------------
    def start(self, interval: int = 5):
        if self._running:
            return
        self.interval = interval
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        if self.debug:
            print(f"[SystemMonitor] started with interval={interval}s")

    def stop(self):
        self._running = False
        if self.debug:
            print("[SystemMonitor] stopped")

    def on_update(self, func):
        """Register callback executed on every update (receives dict)."""
        if func not in self.callbacks:
            self.callbacks.append(func)

    # ------------------------------------------------------------------
    def _loop(self):
        while self._running:
            start_t = time.time()
            try:
                snapshot = self._collect_all()
                self.data = snapshot
                for cb in list(self.callbacks):
                    try:
                        cb(snapshot)
                    except Exception:
                        if self.debug:
                            print("[SystemMonitor] callback error", cb)
            except Exception as e:
                if self.debug:
                    print("[SystemMonitor] loop exception:", e)
            elapsed = max(0, self.interval - (time.time() - start_t))
            time.sleep(elapsed)

    # ------------------------------------------------------------------
    def _collect_all(self):
        # --- External connection checks ---
        conns = {
            "server": self._check_server(),
            "lmstudio": self._check_lmstudio(),
            "sillytavern": self._check_sillytavern(),
            "world": self._check_world(),
        }

        # --- Local hardware metrics ---
        resources = self._collect_system_metrics()

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "connections": conns,
            "resources": resources,
        }

    # ------------------------------------------------------------------
    # Connection checks with latency measurement
    # ------------------------------------------------------------------
    def _check_server(self):
        t0 = time.time()
        try:
            r = requests.get(self.targets["server"], timeout=3)
            latency = (time.time() - t0) * 1000
            if r.status_code == 200:
                return {"state": "online", "latency_ms": round(latency, 1), "metrics": r.json()}
            # fallback to /status
            alt = requests.get(f"{self.api_base}/status", timeout=2)
            if alt.status_code == 200:
                return {"state": "online", "latency_ms": round(latency, 1)}
            return {"state": "warn"}
        except Exception:
            return {"state": "offline"}

    def _check_lmstudio(self):
        t0 = time.time()
        try:
            r = requests.get(self.targets["lmstudio"], timeout=2)
            latency = (time.time() - t0) * 1000
            if r.status_code == 200:
                js = r.json() if "application/json" in r.headers.get("Content-Type", "") else {}
                return {"state": "online", "model": js.get("model", "unknown"), "latency_ms": round(latency, 1)}
        except Exception:
            pass
        return {"state": "offline"}

    def _check_sillytavern(self):
        t0 = time.time()
        try:
            r = requests.get(self.targets["sillytavern"], timeout=2)
            latency = (time.time() - t0) * 1000
            if r.status_code == 200:
                js = r.json()
                if js.get("status") == "ok":
                    return {"state": "online", "latency_ms": round(latency, 1)}
        except Exception:
            pass
        return {"state": "offline"}

    def _check_world(self):
        try:
            r = requests.get(self.targets["world"], timeout=2)
            if r.status_code == 200:
                js = r.json()
                return {"state": js.get("status", "online")}
        except Exception:
            pass
        return {"state": "offline"}

    # ------------------------------------------------------------------
    # Local hardware collection
    # ------------------------------------------------------------------
    def _collect_system_metrics(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            gpus = self._collect_gpu_details()
            gpu_percent = gpus[0]["utilization"] if gpus else 0
            return {
                "cpu_percent": cpu,
                "ram_percent": ram,
                "gpu_percent": gpu_percent,
                "gpus": gpus,
            }
        except Exception as e:
            if self.debug:
                print("[SystemMonitor] metric collection error:", e)
            return {"cpu_percent": 0, "ram_percent": 0, "gpu_percent": 0, "gpus": []}

    def _collect_gpu_details(self):
        """Try torch first, then nvidia-smi."""
        gpus = []
        # --- torch route ---
        try:
            if torch and torch.cuda.is_available():
                count = torch.cuda.device_count()
                for i in range(count):
                    props = torch.cuda.get_device_properties(i)
                    util = torch.cuda.utilization(i) if hasattr(torch.cuda, "utilization") else 0
                    mem_total = props.total_memory / (1024 ** 2)
                    mem_used = torch.cuda.memory_allocated(i) / (1024 ** 2)
                    gpus.append({
                        "id": i,
                        "name": props.name,
                        "utilization": util,
                        "mem_used": round(mem_used, 1),
                        "mem_total": round(mem_total, 1),
                    })
                return gpus
        except Exception:
            pass

        # --- fallback nvidia-smi ---
        try:
            out = subprocess.check_output([
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ], stderr=subprocess.DEVNULL).decode().strip()
            for line in out.splitlines():
                idx, name, util, mem_used, mem_total, temp = [x.strip() for x in line.split(",")]
                gpus.append({
                    "id": int(idx),
                    "name": name,
                    "utilization": int(util),
                    "mem_used": int(mem_used),
                    "mem_total": int(mem_total),
                    "temp_c": int(temp),
                })
        except Exception:
            pass

        return gpus