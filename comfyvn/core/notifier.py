from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/notifier.py
# [COMFYVN Architect | v1.0 | this chat]
from typing import List, Dict
from time import time

class Notifier:
    def __init__(self):
        self.history: List[Dict] = []
        self.enabled = True
    def toast(self, level: str, msg: str):
        evt = {"ts": time(), "level": level, "msg": msg}
        self.history.append(evt)
        print(f"[TOAST] {level}: {msg}")
    def list(self): return list(self.history)

notifier = Notifier()