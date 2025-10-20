from PySide6.QtGui import QAction
import io, hashlib
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from comfyvn.server.core.trash import move_to_trash
from fastapi.responses import FileResponse
from PIL import Image
from comfyvn.server.modules.auth import require_scope

router = APIRouter()
ASSETS = Path("./data/assets").resolve()
THUMBS = (ASSETS / "_thumbs").resolve()
ASSETS.mkdir(parents=True, exist_ok=True); THUMBS.mkdir(parents=True, exist_ok=True)

def _thumb_for(path: Path) -> Path:
    rel = path.relative_to(ASSETS)
    th = THUMBS / rel
    th = th.with_suffix(".png")
    th.parent.mkdir(parents=True, exist_ok=True)
    return th

@router.get("/list")
async def list_assets():
    items = []
    for p in sorted(ASSETS.rglob("*")):
        if p.is_dir() or "_thumbs" in p.parts: continue
        th = _thumb_for(p)
        items.append({"path": str(p.relative_to(ASSETS)), "size": p.stat().st_size, "thumb": str(th.relative_to(ASSETS)) if th.exists() else None})
    return {"ok": True, "items": items}

@router.post("/upload")
async def upload(file: UploadFile = File(...), _: bool = Depends(require_scope(["assets.write"]))):
    data = await file.read()
    name = file.filename or "asset.bin"
    dest = (ASSETS / name).resolve()
    if not str(dest).startswith(str(ASSETS)): raise HTTPException(status_code=400, detail="bad path")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        im = Image.open(io.BytesIO(data)); im.thumbnail((256,256))
        th = _thumb_for(dest); im.save(th, "PNG")
    except Exception: pass
    sha = hashlib.sha256(data).hexdigest()
    return {"ok": True, "path": str(dest.relative_to(ASSETS)), "sha256": sha}

@router.get("/download")
async def download(path: str):
    fp = (ASSETS / path).resolve()
    if not str(fp).startswith(str(ASSETS)): raise HTTPException(status_code=400, detail="bad path")
    if not fp.exists(): raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(fp), filename=fp.name)

@router.delete("/delete")
async def delete(path: str, _: bool = Depends(require_scope(["assets.write"]))):
    fp = (ASSETS / path).resolve()
    if not str(fp).startswith(str(ASSETS)): raise HTTPException(status_code=400, detail="bad path")
    if not fp.exists(): raise HTTPException(status_code=404, detail="not found")
    move_to_trash(fp); return {"ok": True, "trashed": True}