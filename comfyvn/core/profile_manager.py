from __future__ import annotations

# comfyvn/core/profile_manager.py
import json
import time
from pathlib import Path

from PySide6.QtGui import QAction

CONFIG = Path("comfyvn/data/profile.json")


def load_profile() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"theme": "default_dark", "last_project": None, "fast_boot": False}


def save_profile(data: dict):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_profile(key: str, value):
    data = load_profile()
    data[key] = value
    save_profile(data)


def fast_boot_ok() -> bool:
    d = load_profile()
    return d.get("fast_boot", False)
