import json
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

router = APIRouter()
BASE = Path("data/projects")
BASE.mkdir(parents=True, exist_ok=True)
OUT = Path("exports/packages")
OUT.mkdir(parents=True, exist_ok=True)


@router.post("/bundle")
def bundle(payload: dict = Body(...)):
    name = payload.get("name", f"project_{int(time.time())}")
    projdir = BASE / name
    projdir.mkdir(parents=True, exist_ok=True)
    # write manifest
    (projdir / "manifest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    # zip
    zpath = OUT / f"{name}.cvnpack"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in projdir.rglob("*"):
            z.write(p, p.relative_to(projdir))
    return {"ok": True, "file": str(zpath)}
