from PySide6.QtGui import QAction
# comfyvn/core/workspace_templates.py
# [COMFYVN Architect | v1.0 | this chat]
import os, json
from typing import Optional
from PySide6.QtWidgets import QFileDialog
from comfyvn.config.runtime_paths import workspace_dir

def _dir():
    path = workspace_dir()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

def list_templates():
    _dir(); return [f[:-5] for f in os.listdir(DIR) if f.endswith(".json")]

def save_template(name: str, data: dict):
    path = os.path.join(_dir(), f"{name}.json")
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

def load_template(name: str) -> dict:
    with open(os.path.join(_dir(), f"{name}.json"), "r", encoding="utf-8") as f: return json.load(f)

def pick_template_file(parent, open_mode=True) -> Optional[str]:
    _dir()
    if open_mode:
        p,_ = QFileDialog.getOpenFileName(parent, "Open Template", DIR, "JSON (*.json)")
    else:
        p,_ = QFileDialog.getSaveFileName(parent, "Save Template", DIR, "JSON (*.json)")
    return p or None

def load_template_by_path(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f: return json.load(f)
