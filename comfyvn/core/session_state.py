import json
# comfyvn/core/session_state.py
# [COMFYVN Architect | v1.2 | this chat]
import os
from typing import Any, Dict

from PySide6.QtGui import QAction

UI_DIR = os.path.join("data", "ui")
STATE_FILE = os.path.join(UI_DIR, "session.json")


def _ensure():
    os.makedirs(UI_DIR, exist_ok=True)


def load() -> Dict[str, Any]:
    _ensure()
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(data: Dict[str, Any]):
    _ensure()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def update(**kv):
    s = load()
    s.update(kv)
    save(s)
