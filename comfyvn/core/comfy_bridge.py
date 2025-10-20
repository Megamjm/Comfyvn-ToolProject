from __future__ import annotations
from PySide6.QtGui import QAction
from typing import Dict, Any

class ComfyBridge:
    def __init__(self):
        self.base = None

    def set_base(self, base: str):
        self.base = (base or "").rstrip("/")

    def ping(self) -> Dict[str, Any]:
        return {"ok": True, "base": self.base}

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # stub; real impl would POST to ComfyUI queue
        return {"ok": True, "submitted": payload, "base": self.base}