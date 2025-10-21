import json
# comfyvn/core/session_manager.py
# [COMFYVN Architect | v1.3 | this chat]
import os
import time
from typing import Any, Dict, List

from PySide6.QtGui import QAction

BASE_DIR = os.path.join("data", "ui")
FILE = os.path.join(BASE_DIR, "session_v13.json")

DEFAULT = {
    "last_project": None,
    "last_space": None,
    "open_panels": [],  # titles in main window
    "recent_projects": [],  # [{id, ts}]
}


def _ensure():
    os.makedirs(BASE_DIR, exist_ok=True)


def load() -> Dict[str, Any]:
    _ensure()
    if not os.path.exists(FILE):
        return DEFAULT.copy()
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return DEFAULT.copy()


def save(obj: Dict[str, Any]):
    _ensure()
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def update(**kv):
    s = load()
    s.update(kv)
    save(s)


def remember_project(pid: str):
    s = load()
    s["last_project"] = pid
    rp: List[Dict[str, Any]] = s.get("recent_projects", [])
    rp = [x for x in rp if x.get("id") != pid]
    rp.insert(0, {"id": pid, "ts": time.time()})
    s["recent_projects"] = rp[:12]
    save(s)


def remember_space(space: str):
    s = load()
    s["last_space"] = space
    save(s)


def remember_panel_open(title: str):
    s = load()
    p = set(s.get("open_panels", []))
    p.add(title)
    s["open_panels"] = sorted(p)
    save(s)


def remember_panel_closed(title: str):
    s = load()
    p = [x for x in s.get("open_panels", []) if x != title]
    s["open_panels"] = p
    save(s)
