from __future__ import annotations
# comfyvn/core/settings_manager.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import copy
import json
from pathlib import Path

try:
    from PySide6.QtGui import QAction  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover - optional dependency
    QAction = None  # type: ignore

DEFAULTS = {
    "developer": {"verbose": True, "toasts": True, "file_only": False},
    "ui": {"menu_sort_mode": "load_order"},
    "server": {"local_port": 8001},
    "policy": {
        "ack_legal_v1": False,
        "ack_timestamp": None,
        "warn_override_enabled": True,
    },
    "filters": {
        "content_mode": "sfw",  # sfw | warn | unrestricted
    },
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
            if k not in data:
                data[k] = copy.deepcopy(v)
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
