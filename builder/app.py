from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from PySide6.QtGui import QAction

app = FastAPI(title="ComfyVN Builder")


@app.get("/phases")
def phases():
    base = Path(".")
    items = []
    for p in sorted(base.glob("ComfyVN_Phase*")):
        try:
            items.append({"name": p.name, "mtime": p.stat().st_mtime})
        except Exception:
            pass
    return {"ok": True, "items": items}


@app.post("/merge")
def merge(body: dict):
    phases = body.get("phases") or []
    target = Path("./_merged")
    if target.exists():
        shutil.rmtree(target)
    if not phases:
        return {"ok": False, "error": "no phases"}
    for ph in phases:
        rp = (
            Path("/") / "mnt" / "data" / ph
            if ph.startswith("ComfyVN_Phase")
            else Path(ph)
        )
        rp = Path("./") / ph
        if not rp.exists():
            return {"ok": False, "error": f"phase not found {ph}"}
        # naive copy; prefer latest file on conflicts
        for p in rp.rglob("*"):
            if p.is_file():
                out = target / p.relative_to(rp.parent)
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out)
    # Zip
    zpath = Path("./dist")
    zpath.mkdir(parents=True, exist_ok=True)
    zf = zpath / "ComfyVN_merged.zip"
    if zf.exists():
        zf.unlink()
    with zipfile.ZipFile(zf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in target.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(target.parent))
    return {"ok": True, "zip": zf.as_posix()}


app.mount(
    "/",
    StaticFiles(directory=str((Path(__file__).parent / "web")), html=True),
    name="web",
)
