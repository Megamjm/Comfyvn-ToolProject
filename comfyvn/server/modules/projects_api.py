import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PySide6.QtGui import QAction

from comfyvn.server.modules.auth import require_scope

router = APIRouter()
P_DIR = Path("./data/projects")
P_DIR.mkdir(parents=True, exist_ok=True)
CUR = P_DIR / "_current.json"


def _load(name: str) -> Dict[str, Any]:
    p = (P_DIR / f"{name}.json").resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="project not found")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/list")
async def list_projects():
    items = []
    cur = None
    if CUR.exists():
        try:
            cur = json.loads(CUR.read_text(encoding="utf-8")).get("name")
        except Exception:
            cur = None
    for p in sorted(P_DIR.glob("*.json")):
        if p.name == "_current.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        items.append(
            {
                "name": p.stem,
                "scenes": len(data.get("scenes", [])),
                "characters": len(data.get("characters", [])),
                "current": p.stem == cur,
            }
        )
    return {"ok": True, "items": items}


@router.post("/create")
async def create_project(
    body: Dict[str, Any], _: bool = Depends(require_scope(["projects.write"]))
):
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    rec = {
        "name": name,
        "scenes": body.get("scenes") or [],
        "characters": body.get("characters") or [],
        "assets": body.get("assets") or [],
    }
    (P_DIR / f"{name}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return {"ok": True}


@router.post("/select/{name}")
async def select_project(
    name: str, _: bool = Depends(require_scope(["projects.write"]))
):
    CUR.write_text(json.dumps({"name": name}), encoding="utf-8")
    return {"ok": True}


@router.get("/get/{name}")
async def get_project(name: str):
    return _load(name)


@router.get("/export/{name}")
async def export_project(
    name: str, _: bool = Depends(require_scope(["projects.write"]))
):
    data = _load(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(data, indent=2))
        for s in data.get("scenes", []):
            p = Path("./data/scenes") / f"{s}.json"
            if p.exists():
                z.write(p, f"scenes/{p.name}")
        for c in data.get("characters", []):
            p = Path("./data/characters") / f"{c}.json"
            if p.exists():
                z.write(p, f"characters/{p.name}")
        for a in data.get("assets", []):
            p = Path("./data/assets") / a
            if p.exists():
                z.write(p, f"assets/{a}")
    buf.seek(0)
    fp = Path("./exports") / f"project_{name}.zip"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_bytes(buf.getvalue())
    return FileResponse(str(fp), filename=fp.name, media_type="application/zip")


@router.post("/import")
async def import_project(
    file: UploadFile = File(...), _: bool = Depends(require_scope(["projects.write"]))
):
    data = await file.read()
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf) as z:
        pj = json.loads(z.read("project.json").decode("utf-8"))
        name = pj.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="invalid project")
        (P_DIR / f"{name}.json").write_text(json.dumps(pj, indent=2), encoding="utf-8")
        # extract assets/scenes/characters
        for m in z.namelist():
            if m.startswith("scenes/"):
                out = Path("./data/scenes") / Path(m).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(m))
            elif m.startswith("characters/"):
                out = Path("./data/characters") / Path(m).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(m))
            elif m.startswith("assets/"):
                rel = Path(m).relative_to("assets")
                out = Path("./data/assets") / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(m))
    return {"ok": True}
