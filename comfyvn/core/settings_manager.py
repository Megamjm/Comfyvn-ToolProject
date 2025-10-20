from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/settings_manager.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import json
from pathlib import Path

DEFAULTS = {
    "developer": {"verbose": True, "toasts": True, "file_only": False}
}

class SettingsManager:
    def __init__(self, path: str | Path = "data/settings/config.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(DEFAULTS)

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        # backfill defaults
        for k, v in DEFAULTS.items():
            if k not in data: data[k] = v
        return data

    def save(self, data: dict):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self.load().get(key, default)

    def patch(self, key: str, value):
        cfg = self.load()
        cfg[key] = value
        self.save(cfg)
        return cfg