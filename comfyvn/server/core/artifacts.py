from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtGui import QAction

ART_DIR = Path("./data/artifacts")
ART_DIR.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 512), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_path(aid: str) -> Path:
    return ART_DIR / f"{aid}.json"


def register(
    path: str,
    *,
    kind: str = "file",
    run_id: str = "",
    scene_id: str = "",
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": "file not found"}
    aid = hashlib.sha1(
        f"{p.stat().st_mtime_ns}:{p.stat().st_size}:{p.as_posix()}".encode()
    ).hexdigest()[:20]
    rec = {
        "id": aid,
        "run_id": run_id or "",
        "scene_id": scene_id or "",
        "path": p.as_posix(),
        "kind": kind or "file",
        "size": int(p.stat().st_size),
        "sha256": _sha256(p),
        "meta": meta or {},
        "created": time.time(),
    }
    _manifest_path(aid).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return {"ok": True, "item": rec}


def list_local(
    run_id: str = "", scene_id: str = "", kind: str = "", limit: int = 500
) -> Dict[str, Any]:
    items = []
    for mp in sorted(
        ART_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
    ):
        try:
            rec = json.loads(mp.read_text(encoding="utf-8"))
            if run_id and rec.get("run_id") != run_id:
                continue
            if scene_id and rec.get("scene_id") != scene_id:
                continue
            if kind and rec.get("kind") != kind:
                continue
            items.append(rec)
            if len(items) >= limit:
                break
        except Exception:
            continue
    return {"ok": True, "items": items}


def get_local(aid: str) -> Dict[str, Any]:
    mp = _manifest_path(aid)
    if not mp.exists():
        return {"ok": False, "error": "not found"}
    return {"ok": True, "item": json.loads(mp.read_text(encoding="utf-8"))}
