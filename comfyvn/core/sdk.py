from __future__ import annotations
from PySide6.QtGui import QAction
import os, httpx, json
class ComfyVN:
    def __init__(self, base_url=None, token=None, timeout=20.0):
        self.base_url = (base_url or os.getenv("COMFYVN_URL") or "http://localhost:8001").rstrip("/")
        self.token = token or os.getenv("COMFYVN_TOKEN") or ""
        self._c = httpx.Client(timeout=timeout)
    def _h(self):
        h={"Content-Type":"application/json"}
        if self.token: h["Authorization"]="Bearer "+self.token
        return h
    def login(self, email, password):
        r=self._c.post(self.base_url+"/auth/login", headers=self._h(), json={"email":email,"password":password}); r.raise_for_status()
        self.token=r.json().get("token",""); return self.token
    def scene_list(self, limit=100):
        r=self._c.get(self.base_url+"/db/scenes/list", headers=self._h(), params={"limit":limit}); r.raise_for_status(); return r.json()