from __future__ import annotations

# comfyvn/core/workspace_manager.py
# [COMFYVN Architect | v0.8.5 | this chat]
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtGui import QAction

from comfyvn.config.runtime_paths import settings_file

WS_FILE = settings_file("workspace.json")

DEFAULTS = {
    "open_panels": [],  # ["timeline_view","lore_view"]
    "geometry": None,  # reserved for future (Qt saveState/saveGeometry)
    "last_project": None,
}


def load() -> Dict[str, Any]:
    if WS_FILE.exists():
        try:
            return json.loads(WS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULTS)


def save(state: Dict[str, Any]):
    WS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WS_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def add_panel(panel_id: str):
    st = load()
    if panel_id not in st.get("open_panels", []):
        st["open_panels"].append(panel_id)
        save(st)


def remove_panel(panel_id: str):
    st = load()
    st["open_panels"] = [p for p in st.get("open_panels", []) if p != panel_id]
    save(st)


def set_last_project(project_id: str | None):
    st = load()
    st["last_project"] = project_id
    save(st)


def get_last_project() -> str | None:
    return load().get("last_project")
