from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/spaces_presets.py
from pathlib import Path
import json

PRESETS = {
    "Render Space": ["GPU / Local", "GPU / Remote", "Render Queue"],
    "Import Space": ["Assets", "Timeline"],
    "Remote Space": ["Server Control", "GPU / Remote"],
    "Config Space": ["Settings", "Extensions"]
}

def save_presets():
    base = Path("data/workspaces/presets")
    base.mkdir(parents=True, exist_ok=True)
    for name, panels in PRESETS.items():
        (base / f"{name}.json").write_text(json.dumps({"panels": panels}, indent=2), encoding="utf-8")

def list_presets():
    base = Path("data/workspaces/presets")
    if not base.exists(): return []
    return [p.stem for p in base.glob("*.json")]

def load_preset(name: str):
    base = Path("data/workspaces/presets") / f"{name}.json"
    if not base.exists(): return {}
    return json.loads(base.read_text(encoding="utf-8"))