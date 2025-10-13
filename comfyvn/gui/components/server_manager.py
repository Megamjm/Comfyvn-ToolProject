# comfyvn/gui/components/server_manager.py
# 🧩 ServerManager — Embedded FastAPI/Uvicorn process control
# [COMFYVN Architect | Phase 3.3 Integration-Synced]

import os, psutil, requests, subprocess, time


class ServerManager:
    """Controls the embedded FastAPI (ComfyVN) server lifecycle."""

    def __init__(self, host="127.0.0.1", port=8001):
        self.host = host
        self.port = port
        self.proc = None
        self.status = "stopped"

    # ------------------------------------------------------------
    # Launch & lifecycle
    # ------------------------------------------------------------
    def start(self, mode="embedded"):
        """Start the ComfyVN FastAPI server."""
        if self.is_running():
            return f"Server already running at {self.host}:{self.port}"
        try:
            self.proc = subprocess.Popen(
                ["python", "-m", "comfyvn.app"],
                stdout=open(log_path, "ab"),
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.status = "running"
            time.sleep(1.5)
            return f"Started {mode} server on {self.host}:{self.port}"
        except Exception as e:
            self.status = "error"
            return f"❌ Failed to start server: {e}"

    def restart(self):
        """Restart the server process."""
        self.stop(force=True)
        time.sleep(1)
        return self.start("restart")

    def stop(self, force=False):
        """Stop the running server gracefully or forcefully."""
        if not self.is_running():
            return "Server not running."
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            self.status = "stopped"
            return "🟡 Server stopped gracefully."
        except Exception as e:
            if force:
                return self.force_kill_all()
            return f"⚠️ Error stopping server: {e}"

    # ------------------------------------------------------------
    # Force kill (Windows-safe)
    # ------------------------------------------------------------
    def force_kill_all(self):
        """Brute-force kill all ComfyVN-related processes (cross-platform safe)."""
        killed = 0
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline")
                if not isinstance(cmdline, (list, tuple)):
                    continue
                cmd = " ".join(cmdline)
                if "comfyvn.app" in cmd or "uvicorn" in cmd:
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
                continue
        self.status = "stopped"
        return f"💀 Killed {killed} residual server processes."

    # ------------------------------------------------------------
    # Status & health
    # ------------------------------------------------------------
    def is_running(self):
        """Check if the server process is alive or port is occupied."""
        if self.proc and self.proc.poll() is None:
            return True
        # Fallback: detect active process by port usage
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline", []))
                if f":{self.port}" in cmd:
                    return True
            except Exception:
                continue
        return False

    def ping(self):
        """Quick health check to the running API."""
        try:
            url = f"http://{self.host}:{self.port}/health"
            r = requests.get(url, timeout=2)
            return r.status_code == 200
        except Exception:
            return False
