from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtGui import QAction

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
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            obj = {}
    obj.setdefault("scene_id", scene_id)
    obj.setdefault("id", obj.get("scene_id"))
    obj.setdefault("title", scene_id)

    if not isinstance(obj.get("nodes"), list):
        obj["nodes"] = []

    if not isinstance(obj.get("lines"), list):
        obj["lines"] = []

    lines_out: List[Dict[str, Any]] = []
    for index, entry in enumerate(obj["lines"]):
        if isinstance(entry, dict):
            if not entry.get("line_id"):
                entry = dict(entry)
                entry["line_id"] = entry.get("id") or f"{scene_id}_line_{index}"
            lines_out.append(entry)
        elif isinstance(entry, str):
            lines_out.append(
                {
                    "line_id": f"{scene_id}_line_{index}",
                    "speaker": "Narrator",
                    "text": entry,
                }
            )
        else:
            continue
    obj["lines"] = lines_out

    if not isinstance(obj.get("order"), list):
        obj["order"] = [
            line.get("line_id") or str(index)
            for index, line in enumerate(obj["lines"])
            if isinstance(line, dict)
        ]

    if not isinstance(obj.get("meta"), dict):
        obj["meta"] = {}

    obj.setdefault("start", obj.get("start") or "")

    lamport = obj.get("lamport") or obj.get("clock") or obj.get("version") or 0
    try:
        lamport = int(lamport)
    except Exception:
        lamport = 0
    obj["lamport"] = lamport
    obj["version"] = int(obj.get("version") or 0)
    return obj


def scene_save(
    scene: Dict[str, Any], *, expected_version: int | None = None
) -> Dict[str, Any]:
    scene_id = str(scene.get("scene_id") or scene.get("id") or "default")
    with _lock(scene_id):
        cur = scene_load(scene_id)
        cur_ver = int(cur.get("version") or 0)
        if expected_version is not None and expected_version != cur_ver:
            raise ValueError(
                f"version_conflict: expected {expected_version}, got {cur_ver}"
            )
        new = dict(cur)
        if "title" in scene:
            new["title"] = scene["title"]
        if "start" in scene:
            new["start"] = scene["start"]
        if isinstance(scene.get("lines"), list):
            new["lines"] = scene["lines"]
        if isinstance(scene.get("nodes"), list):
            new["nodes"] = scene["nodes"]
        if isinstance(scene.get("order"), list):
            new["order"] = scene["order"]
        if isinstance(scene.get("meta"), dict):
            new["meta"] = scene["meta"]

        new["scene_id"] = scene_id
        new["id"] = new.get("id") or scene.get("id") or scene_id

        lamport_raw = scene.get("lamport") or scene.get("clock")
        has_crdt_metadata = (
            lamport_raw is not None
            or "nodes" in scene
            or "order" in scene
            or "meta" in scene
        )
        if has_crdt_metadata:
            try:
                lamport_val = int(
                    lamport_raw if lamport_raw is not None else cur.get("lamport", 0)
                )
            except Exception:
                lamport_val = int(cur.get("lamport") or 0)
            new["lamport"] = lamport_val
            if scene.get("version") is not None:
                try:
                    new["version"] = int(scene["version"])
                except Exception:
                    new["version"] = cur_ver + 1
            else:
                new["version"] = cur_ver + 1
        else:
            new.pop("lamport", None)
            new["version"] = cur_ver + 1

        p = _path(scene_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(new, indent=2), encoding="utf-8")
        return new


def list_scenes() -> List[str]:
    _ROOT.mkdir(parents=True, exist_ok=True)
    return sorted([p.stem for p in _ROOT.glob("*.json")])
