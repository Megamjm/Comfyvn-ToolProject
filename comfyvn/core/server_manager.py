from PySide6.QtGui import QAction
# comfyvn/core/server_manager.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import subprocess, sys, os, signal, requests
class ServerManager:
    def __init__(self): self.proc=None; self.host="127.0.0.1"; self.port=8001
    def start(self, host="127.0.0.1", port=8001):
        if self.is_running(): return True
        self.host, self.port = host, port
        cmd=[sys.executable,"-m","uvicorn","comfyvn.server.app:app","--host",host,"--port",str(port)]
        try:
            self.proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except FileNotFoundError:
            self.proc=None; return False
    def stop(self):
        if not self.is_running(): return
        try:
            if os.name=="nt": self.proc.terminate()
            else: os.kill(self.proc.pid, signal.SIGTERM)
        except Exception: pass
        self.proc=None
    def is_running(self): 
        return self.proc is not None and (self.proc.poll() is None)
    def health(self):
        try:
            r=requests.get(f"http://{self.host}:{self.port}/health", timeout=0.75)
            if r.status_code==200:
                b=r.json(); return {"ok":True, "version": b.get("version","?")}
        except Exception: pass
        return {"ok": False}