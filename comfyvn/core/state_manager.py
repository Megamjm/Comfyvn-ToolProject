from PySide6.QtGui import QAction

from pathlib import Path
import json, time

class StateManager:
    def __init__(self, base="data/state"):
        self.base = Path(base); self.base.mkdir(parents=True, exist_ok=True)
    def save(self, name: str, data):
        p = self.base / f"{name}.json"
        p.write_text(json.dumps({"ts": time.time(), "data": data}, indent=2), encoding="utf-8")
        return str(p)
    def load(self, name: str, default=None):
        p = self.base / f"{name}.json"
        if not p.exists(): return default
        return json.loads(p.read_text(encoding="utf-8"))