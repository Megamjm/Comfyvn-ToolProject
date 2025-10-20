from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/space_manager.py
import json, time
from pathlib import Path
SPACES_DIR = Path("data/settings/spaces")
SPACES_DIR.mkdir(parents=True, exist_ok=True)

def _file(name: str) -> Path: return SPACES_DIR / f"{name}.json"

def list_spaces() -> list[str]:
    return [p.stem for p in SPACES_DIR.glob("*.json")]

def load(name: str) -> dict:
    p = _file(name)
    if not p.exists(): return {"name": name, "open_panels": [], "geometry": None}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {"name": name, "open_panels": []}

def save(name: str, state: dict):
    state["last_used"] = time.time()
    _file(name).write_text(json.dumps(state, indent=2), encoding="utf-8")

def delete(name: str):
    try: _file(name).unlink()
    except FileNotFoundError: pass