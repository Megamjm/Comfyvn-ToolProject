from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/comfyui_client.py
import requests

class ComfyUIClient:
    def __init__(self, base: str = "http://127.0.0.1:8188"):
        self.base = base.rstrip("/")

    def health(self, timeout: float = 1.5) -> bool:
        try:
            r = requests.get(self.base, timeout=timeout)
            return r.status_code < 500
        except Exception:
            return False

    def submit_workflow(self, wf: dict, timeout: float = 5.0) -> dict:
        # placeholder — adapt to ComfyUI API schema
        try:
            r = requests.post(self.base + "/prompt", json=wf, timeout=timeout)
            return {"ok": r.status_code < 400, "raw": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_history(self, job_id: str, timeout: float = 3.0) -> dict:
        try:
            r = requests.get(self.base + f"/history/{job_id}", timeout=timeout)
            return {"ok": r.status_code < 400, "data": r.json() if r.ok else {}}
        except Exception as e:
            return {"ok": False, "error": str(e)}