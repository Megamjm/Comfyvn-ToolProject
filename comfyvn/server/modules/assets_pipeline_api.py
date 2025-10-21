from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Body, Request
from PySide6.QtGui import QAction

from comfyvn.core.asset_index import AssetIndex

router = APIRouter(prefix="/assets", tags=["assets"])
_index = AssetIndex()


@router.post("/index")
def build_index(payload: Dict[str, Any] = Body(default={})):
    root = payload.get("root")
    if root:
        _index.root = Path(root)
        _index.index_file = Path(root) / "_index.json"
    return {"ok": True, "index": _index.build()}


@router.get("/index")
def read_index():
    return {"ok": True, "index": _index.read()}


@router.post("/workflow/register")
def workflow_register(payload: Dict[str, Any] = Body(...)):
    name = str(payload.get("name") or "").strip()
    path = str(payload.get("path") or "").strip()
    if not name or not path:
        return {"ok": False, "error": "name and path required"}
    wfdir = Path("data/workflows")
    wfdir.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "path": path}
    (wfdir / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "workflow": meta}


@router.post("/render")
def render_request(request: Request, payload: Dict[str, Any] = Body(...)):
    jm = getattr(request.app.state, "job_manager", None)
    job_payload = {
        "id": payload.get("id"),
        "workflow": payload.get("workflow"),
        "prompt": payload.get("prompt", {}),
        "device": payload.get("device", "cpu"),
    }
    if jm and hasattr(jm, "enqueue"):
        jid = jm.enqueue("render.request", job_payload, retries=2, priority=1)
        return {"ok": True, "queued": True, "job_id": jid}
    return {
        "ok": True,
        "queued": False,
        "reason": "job_manager_unavailable",
        "request": job_payload,
    }


@router.post("/sprite")
def sprite_lookup_or_enqueue(request: Request, payload: Dict[str, Any] = Body(...)):
    char = str(payload.get("char") or "").strip()
    mood = str(payload.get("mood") or "").strip()
    if not char or not mood:
        return {"ok": False, "error": "char and mood required"}
    p = _index.sprite_path(char, mood)
    if p.exists():
        return {"ok": True, "cached": True, "path": str(p)}
    jm = getattr(request.app.state, "job_manager", None)
    if jm and hasattr(jm, "enqueue"):
        jid = jm.enqueue(
            "sprite.render", {"char": char, "mood": mood, "out": str(p)}, retries=2
        )
        return {
            "ok": True,
            "cached": False,
            "queued": True,
            "job_id": jid,
            "expected": str(p),
        }
    return {"ok": True, "cached": False, "queued": False, "expected": str(p)}
