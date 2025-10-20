from __future__ import annotations
from PySide6.QtGui import QAction
import io, zipfile, time
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from comfyvn.server.modules.auth import require_scope

router = APIRouter()
VDIR = Path("./data/versions"); VDIR.mkdir(parents=True, exist_ok=True)

INCLUDE_DIRS = ["data/scenes", "data/characters", "data/assets", "exports/renders"]

def _snap_name(name: str | None = None) -> str:
    base = f"snap_{int(time.time())}"
    return f"{base}_{name}.zip" if name else f"{base}.zip"

@router.get("/list")
async def list_snaps():
    items = []
    for p in sorted(VDIR.glob("snap_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        items.append({"file": p.name, "size": p.stat().st_size, "t": p.stat().st_mtime})
    return {"ok": True, "items": items}

@router.post("/snapshot")
async def snapshot(body: Dict[str, Any] | None = None, _: bool = Depends(require_scope(["projects.write"]))):
    name = (body or {}).get("name")
    fn = _snap_name(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root in INCLUDE_DIRS:
            r = Path(root)
            if not r.exists(): continue
            for p in r.rglob("*"):
                if p.is_file():
                    z.write(p, p.as_posix())
    buf.seek(0)
    out = VDIR / fn; out.write_bytes(buf.getvalue())
    return {"ok": True, "file": out.name, "size": out.stat().st_size}

@router.get("/download/{file}")
async def download(file: str):
    fp = (VDIR / file).resolve()
    if not str(fp).startswith(str(VDIR)): raise HTTPException(status_code=400, detail="bad path")
    if not fp.exists(): raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(fp), filename=fp.name, media_type="application/zip")

@router.post("/restore/{file}")
async def restore(file: str, _: bool = Depends(require_scope(["projects.write"]))):
    fp = (VDIR / file).resolve()
    if not str(fp).startswith(str(VDIR)): raise HTTPException(status_code=400, detail="bad path")
    if not fp.exists(): raise HTTPException(status_code=404, detail="not found")
    with zipfile.ZipFile(fp, "r") as z:
        for m in z.namelist():
            if any(m.startswith(d + "/") for d in INCLUDE_DIRS):
                out = Path(m); out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(z.read(m))
    return {"ok": True, "restored": file}