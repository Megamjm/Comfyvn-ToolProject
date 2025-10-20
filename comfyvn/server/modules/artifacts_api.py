from __future__ import annotations
from PySide6.QtGui import QAction
import json, os
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from comfyvn.server.modules.auth import require_scope
from comfyvn.server.core.artifacts import register, list_local, get_local
from comfyvn.server.core.db import is_enabled, get_db, init_db, ArtifactRow, as_json_str, from_json_str
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/put")
async def put(body: Dict[str, Any], _: bool = Depends(require_scope(["artifacts.write"])), db: Session = Depends(get_db)):
    path = str(body.get("path") or "")
    kind = str(body.get("kind") or "file")
    run_id = str(body.get("run_id") or "")
    scene_id = str(body.get("scene_id") or "")
    meta = body.get("meta") or {}
    j = register(path, kind=kind, run_id=run_id, scene_id=scene_id, meta=meta)
    if not j.get("ok"): raise HTTPException(status_code=400, detail=j.get("error","error"))
    item = j["item"]
    if is_enabled():
        init_db()
        try:
            r = ArtifactRow(art_id=item["id"], run_id=run_id, scene_id=scene_id, kind=kind, path=item["path"], size=item["size"], sha256=item["sha256"], meta=as_json_str(meta))
            db.add(r); db.commit()
        except Exception:
            db.rollback()
    return {"ok": True, "item": item}

@router.get("/list")
async def list_items(run_id: str = "", scene_id: str = "", kind: str = "", limit: int = 200, db: Session = Depends(get_db)):
    if is_enabled():
        init_db()
        try:
            q = db.query(ArtifactRow)
            if run_id: q = q.filter(ArtifactRow.run_id==run_id)
            if scene_id: q = q.filter(ArtifactRow.scene_id==scene_id)
            if kind: q = q.filter(ArtifactRow.kind==kind)
            q = q.order_by(ArtifactRow.id.desc()).limit(min(limit, 1000))
            items = []
            for r in q.all():
                items.append({"id": r.art_id, "run_id": r.run_id, "scene_id": r.scene_id, "kind": r.kind, "path": r.path, "size": r.size, "sha256": r.sha256, "meta": json.loads(r.meta or "{}"), "created": r.created})
            return {"ok": True, "items": items}
        except Exception:
            pass
    return list_local(run_id, scene_id, kind, limit)

@router.get("/get/{aid}")
async def get_one(aid: str):
    j = get_local(aid)
    if not j.get("ok"): raise HTTPException(status_code=404, detail="not found")
    return j

# Linkage helpers
@router.post("/link")
async def link(body: Dict[str, Any], _: bool = Depends(require_scope(["artifacts.write"])), db: Session = Depends(get_db)):
    # Update DB record if exists, else patch local manifest
    aid = str(body.get("id") or "")
    run_id = str(body.get("run_id") or "")
    scene_id = str(body.get("scene_id") or "")
    updated = False
    if is_enabled():
        init_db()
        try:
            r = db.query(ArtifactRow).filter_by(art_id=aid).first()
            if r:
                if run_id: r.run_id = run_id
                if scene_id: r.scene_id = scene_id
                db.commit(); updated = True
        except Exception:
            db.rollback()
    # local patch
    from pathlib import Path
    mp = Path("./data/artifacts") / f"{aid}.json"
    if mp.exists():
        import json as _j
        m = _j.loads(mp.read_text(encoding="utf-8"))
        if run_id: m["run_id"] = run_id
        if scene_id: m["scene_id"] = scene_id
        mp.write_text(_j.dumps(m, indent=2), encoding="utf-8")
        updated = True
    if not updated: raise HTTPException(status_code=404, detail="artifact not found")
    return {"ok": True}