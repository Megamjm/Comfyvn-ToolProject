from __future__ import annotations

import json
# comfyvn/core/spaces_presets.py
from pathlib import Path

from PySide6.QtGui import QAction

from comfyvn.config.runtime_paths import workspace_dir

PRESETS = {
    "Render Space": ["GPU / Local", "GPU / Remote", "Render Queue"],
    "Import Space": ["Assets", "Timeline"],
    "Remote Space": ["Server Control", "GPU / Remote"],
    "Config Space": ["Settings", "Extensions"],
}


def save_presets():
    base = workspace_dir("presets")
    base.mkdir(parents=True, exist_ok=True)
    for name, panels in PRESETS.items():
        (base / f"{name}.json").write_text(
            json.dumps({"panels": panels}, indent=2), encoding="utf-8"
        )


def list_presets():
    base = workspace_dir("presets")
    if not base.exists():
        return []
    return [p.stem for p in base.glob("*.json")]


def load_preset(name: str):
    base = workspace_dir("presets") / f"{name}.json"
    if not base.exists():
        return {}
    return json.loads(base.read_text(encoding="utf-8"))
