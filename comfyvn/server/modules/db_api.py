from __future__ import annotations
from PySide6.QtGui import QAction
import json, time
from typing import Dict, Any, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from comfyvn.server.modules.auth import require_scope
from comfyvn.server.core.db import init_db, get_db, is_enabled, SceneRow, CharacterRow, TokenRow, RunRow, as_json_str, from_json_str

router = APIRouter()

@router.get("/status")
async def status(db: Session = Depends(get_db)):
    init_db()
    counts = {}
    for model, key in [(SceneRow,"scenes"),(CharacterRow,"characters"),(TokenRow,"tokens"),(RunRow,"runs")]:
        try:
            counts[key] = db.query(model).count()
        except Exception:
            counts[key] = 0
    return {"ok": True, "enabled": is_enabled(), "counts": counts}

# --- Scenes ---
@router.get("/scenes/list")
async def scenes_list(db: Session = Depends(get_db)):
    rows = db.query(SceneRow).order_by(SceneRow.updated.desc()).limit(500).all()
    return {"ok": True, "items": [{"scene_id": r.scene_id, "tags": json.loads(r.tags or "[]"), "updated": r.updated} for r in rows]}

@router.get("/scenes/get/{scene_id}")
async def scenes_get(scene_id: str, db: Session = Depends(get_db)):
    r = db.query(SceneRow).filter_by(scene_id=scene_id).first()
    if not r: raise HTTPException(status_code=404, detail="not found")
    return json.loads(r.data)

@router.post("/scenes/upsert/{scene_id}")
async def scenes_upsert(scene_id: str, body: Dict[str, Any], db: Session = Depends(get_db), _: bool = Depends(require_scope(["content.write"]))):
    r = db.query(SceneRow).filter_by(scene_id=scene_id).first()
    tags = json.dumps((body.get("tags") or []), ensure_ascii=False)
    if r:
        r.data = as_json_str(body); r.tags = tags; r.updated = time.time()
    else:
        r = SceneRow(scene_id=scene_id, data=as_json_str(body), tags=tags, created=time.time(), updated=time.time())
        db.add(r)
    db.commit(); return {"ok": True}

@router.delete("/scenes/delete/{scene_id}")
async def scenes_delete(scene_id: str, db: Session = Depends(get_db), _: bool = Depends(require_scope(["content.write"]))):
    r = db.query(SceneRow).filter_by(scene_id=scene_id).first()
    if not r: return {"ok": True}
    db.delete(r); db.commit(); return {"ok": True}

# --- Characters ---
@router.get("/characters/list")
async def characters_list(db: Session = Depends(get_db)):
    rows = db.query(CharacterRow).order_by(CharacterRow.updated.desc()).limit(500).all()
    return {"ok": True, "items": [{"name": r.name, "tags": json.loads(r.tags or "[]"), "updated": r.updated} for r in rows]}

@router.get("/characters/get/{name}")
async def characters_get(name: str, db: Session = Depends(get_db)):
    r = db.query(CharacterRow).filter_by(name=name).first()
    if not r: raise HTTPException(status_code=404, detail="not found")
    return json.loads(r.data)

@router.post("/characters/upsert/{name}")
async def characters_upsert(name: str, body: Dict[str, Any], db: Session = Depends(get_db), _: bool = Depends(require_scope(["content.write"]))):
    r = db.query(CharacterRow).filter_by(name=name).first()
    tags = json.dumps((body.get("tags") or []), ensure_ascii=False)
    if r:
        r.data = as_json_str(body); r.tags = tags; r.updated = time.time()
    else:
        r = CharacterRow(name=name, data=as_json_str(body), tags=tags, created=time.time(), updated=time.time())
        db.add(r)
    db.commit(); return {"ok": True}

@router.delete("/characters/delete/{name}")
async def characters_delete(name: str, db: Session = Depends(get_db), _: bool = Depends(require_scope(["content.write"]))):
    r = db.query(CharacterRow).filter_by(name=name).first()
    if not r: return {"ok": True}
    db.delete(r); db.commit(); return {"ok": True}

# --- Sync utilities ---
@router.post("/sync/files-to-db")
async def sync_files_to_db(db: Session = Depends(get_db), _: bool = Depends(require_scope(["content.write"]))):
    # scenes
    sdir = Path("./data/scenes"); sdir.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in sdir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            scene_id = data.get("scene_id") or p.stem
            tags = json.dumps((data.get("tags") or []), ensure_ascii=False)
            r = db.query(SceneRow).filter_by(scene_id=scene_id).first()
            if r:
                r.data = json.dumps(data, ensure_ascii=False); r.tags = tags; r.updated = time.time()
            else:
                db.add(SceneRow(scene_id=scene_id, data=json.dumps(data, ensure_ascii=False), tags=tags, created=time.time(), updated=time.time()))
            count += 1
        except Exception:
            pass
    # characters
    cdir = Path("./data/characters"); cdir.mkdir(parents=True, exist_ok=True)
    for p in cdir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            name = data.get("name") or p.stem
            tags = json.dumps((data.get("tags") or []), ensure_ascii=False)
            r = db.query(CharacterRow).filter_by(name=name).first()
            if r:
                r.data = json.dumps(data, ensure_ascii=False); r.tags = tags; r.updated = time.time()
            else:
                db.add(CharacterRow(name=name, data=json.dumps(data, ensure_ascii=False), tags=tags, created=time.time(), updated=time.time()))
            count += 1
        except Exception:
            pass
    db.commit()
    return {"ok": True, "imported": count}

@router.post("/sync/db-to-files")
async def sync_db_to_files(db: Session = Depends(get_db), _: bool = Depends(require_scope(["content.write"]))):
    sdir = Path("./data/scenes"); sdir.mkdir(parents=True, exist_ok=True)
    cdir = Path("./data/characters"); cdir.mkdir(parents=True, exist_ok=True)
    sc = 0; cc = 0
    for r in db.query(SceneRow).all():
        try:
            data = json.loads(r.data)
            (sdir / f"{r.scene_id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            sc += 1
        except Exception:
            pass
    for r in db.query(CharacterRow).all():
        try:
            data = json.loads(r.data)
            (cdir / f"{r.name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            cc += 1
        except Exception:
            pass
    return {"ok": True, "scenes": sc, "characters": cc}