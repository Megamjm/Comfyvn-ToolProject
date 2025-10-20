from __future__ import annotations
from PySide6.QtGui import QAction
import json, threading
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path("./data/scenes")
_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()

def _path(scene_id: str) -> Path:
    return _ROOT / f"{scene_id}.json"

def _lock(scene_id: str) -> threading.Lock:
    with _GUARD:
        _LOCKS.setdefault(scene_id, threading.Lock())
        return _LOCKS[scene_id]

def scene_load(scene_id: str) -> Dict[str, Any]:
    p = _path(scene_id)
    obj = {}
    if p.exists():
        try: obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception: obj = {}
    obj.setdefault("scene_id", scene_id)
    obj.setdefault("title", scene_id)
    obj.setdefault("lines", [])
    obj["version"] = int(obj.get("version") or 0)
    return obj

def scene_save(scene: Dict[str, Any], *, expected_version: int | None = None) -> Dict[str, Any]:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "default")
    with _lock(scene_id):
        cur = scene_load(scene_id)
        cur_ver = int(cur.get("version") or 0)
        if expected_version is not None and expected_version != cur_ver:
            raise ValueError(f"version_conflict: expected {expected_version}, got {cur_ver}")
        new = dict(cur)
        if "title" in scene: new["title"] = scene["title"]
        if isinstance(scene.get("lines"), list): new["lines"] = scene["lines"]
        new["scene_id"] = scene_id
        new["version"] = cur_ver + 1
        p = _path(scene_id); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(new, indent=2), encoding="utf-8")
        return new

def list_scenes() -> List[str]:
    _ROOT.mkdir(parents=True, exist_ok=True)
    return sorted([p.stem for p in _ROOT.glob("*.json")])