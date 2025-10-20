from __future__ import annotations
from PySide6.QtGui import QAction
from typing import Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from comfyvn.server.modules.auth import require_scope
from comfyvn.server.core.importers import (
    import_csv, import_jsonl, import_markdown, import_discord_json, import_slack_json, import_telegram_json,
    export_jsonl, export_markdown, export_csv, lines_to_scene, merge_into_scene
)
import json, time, os

router = APIRouter()
DATA_DIR = Path("./data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
SCENES_DIR = DATA_DIR / "scenes"; SCENES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR = DATA_DIR / "exports"; EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
SPEAKERS_FILE = DATA_DIR / "speakers.json"

def _load_text_or_path(body: Dict[str,Any]) -> str:
    if body.get("content_text"):
        return str(body["content_text"])
    p = body.get("content_path")
    if p:
        path = Path(p)
        if not path.exists(): raise HTTPException(400, "content_path not found")
        return path.read_text(encoding="utf-8", errors="replace")
    raise HTTPException(400, "content_text or content_path required")

def _load_speaker_dict() -> Dict[str,str]:
    try: return json.loads(SPEAKERS_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

def _save_speaker_dict(sd: Dict[str,str]):
    SPEAKERS_FILE.write_text(json.dumps(sd, indent=2, ensure_ascii=False), encoding="utf-8")

@router.get("/speakers")
async def speakers_list():
    return {"ok": True, "dict": _load_speaker_dict()}

@router.post("/speakers/put")
async def speakers_put(body: Dict[str,Any], _: bool = Depends(require_scope(["content.write"], cost=5))):
    if not isinstance(body, dict): raise HTTPException(400, "body must be object")
    sd = _load_speaker_dict(); sd.update({k: str(v) for k,v in (body or {}).items()})
    _save_speaker_dict(sd); return {"ok": True}

def _parse(source: str, text: str, sd: Dict[str,str]) -> list[dict]:
    source = (source or "").lower()
    if source == "csv": return import_csv(text, sd)
    if source == "jsonl": return import_jsonl(text, sd)
    if source == "markdown": return import_markdown(text, sd)
    if source == "discord": return import_discord_json(text, sd)
    if source == "slack": return import_slack_json(text, sd)
    if source == "telegram": return import_telegram_json(text, sd)
    raise HTTPException(400, "unknown source")

@router.post("/import/{source}")
async def do_import(source: str, body: Dict[str,Any], _: bool = Depends(require_scope(["content.write"], cost=5))):
    text = _load_text_or_path(body)
    sd = _load_speaker_dict()
    # allow per-request dict override/extend
    if isinstance(body.get("speaker_dict"), dict):
        sd.update({k: str(v) for k,v in body["speaker_dict"].items()})
    lines = _parse(source, text, sd)
    scene_id = str(body.get("scene_id") or f"import_{int(time.time())}")
    project_id = str(body.get("project_id") or "")
    title = str(body.get("title") or f"Imported {source}")
    policy = str(body.get("merge_policy") or "append")
    sp = SCENES_DIR / f"{scene_id}.json"
    sc = merge_into_scene(sp, lines, policy=policy)
    if project_id:
        sc["project_id"] = project_id
        tags = set(sc.get("tags") or []); tags.add(f"project:{project_id}"); sc["tags"] = sorted(list(tags))
    if title: sc["title"] = title
    sp.write_text(json.dumps(sc, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "scene_id": scene_id, "count": len(lines), "path": sp.as_posix()}

@router.get("/export/{target}")
async def do_export(target: str, scene_id: str):
    sp = SCENES_DIR / f"{scene_id}.json"
    if not sp.exists(): raise HTTPException(404, "scene not found")
    sc = json.loads(sp.read_text(encoding="utf-8", errors="replace"))
    lines = sc.get("lines") or []
    tgt = target.lower()
    if tgt == "jsonl":
        content = export_jsonl(lines); ext = "jsonl"
    elif tgt == "markdown":
        content = export_markdown(lines); ext = "md"
    elif tgt == "csv":
        content = export_csv(lines); ext = "csv"
    else:
        raise HTTPException(400, "unknown target")
    op = EXPORTS_DIR / f"{scene_id}.{ext}"
    op.write_text(content, encoding="utf-8")
    return {"ok": True, "path": op.as_posix(), "bytes": len(content.encode('utf-8'))}

@router.post("/export/batch")
async def export_batch(body: Dict[str,Any]):
    target = str(body.get("target") or "jsonl").lower()
    ids = body.get("scene_ids") or []
    if not ids: raise HTTPException(400, "scene_ids required")
    import zipfile
    zp = EXPORTS_DIR / f"batch_{int(time.time())}.zip"
    if zp.exists(): zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for sid in ids:
            try:
                r = await do_export(target, sid)  # reuse
                p = Path(r["path"])
                z.write(p, p.name)
            except Exception:
                continue
    return {"ok": True, "path": zp.as_posix()}

@router.get("/scene/get")
async def scene_get(scene_id: str):
    sp = SCENES_DIR / f"{scene_id}.json"
    if not sp.exists(): raise HTTPException(404, "scene not found")
    try: sc = json.loads(sp.read_text(encoding="utf-8", errors="replace"))
    except Exception: sc = {"scene_id": scene_id, "lines": []}
    return {"ok": True, "scene": sc}