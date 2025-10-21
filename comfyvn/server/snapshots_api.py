from __future__ import annotations

import os
import tarfile
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from PySide6.QtGui import QAction

router = APIRouter(prefix="/snapshot", tags=["Snapshots"])

SNAP_DIR = Path("data/snapshots")
SNAP_DIR.mkdir(parents=True, exist_ok=True)


def _snap_path(name: str) -> Path:
    safe = (
        "".join(c for c in name if c.isalnum() or c in ("-", "_", ".")).strip()
        or "snapshot"
    )
    return SNAP_DIR / f"{safe}.tar.gz"


@router.get("/list")
def list_snaps():
    items = []
    for p in SNAP_DIR.glob("*.tar.gz"):
        st = p.stat()
        items.append(
            {"name": p.stem, "file": p.name, "size": st.st_size, "ts": int(st.st_mtime)}
        )
    items.sort(key=lambda x: x["ts"], reverse=True)
    return {"snapshots": items}


@router.post("/create")
def create_snap(name: str = Body(..., embed=True)):
    path = _snap_path(name)
    with tarfile.open(path, "w:gz") as tf:
        for rel in ["data/flows", "data/state", "configs"]:
            d = Path(rel)
            if d.exists():
                tf.add(str(d), arcname=str(d))
    return {"ok": True, "name": path.stem, "file": path.name}


@router.post("/restore")
def restore_snap(
    snap_id: str = Body(..., embed=True), overwrite: bool = Body(False, embed=True)
):
    path = _snap_path(snap_id)
    if not path.exists():
        raise HTTPException(404, f"snapshot not found: {snap_id}")
    with tarfile.open(path, "r:gz") as tf:
        tf.extractall(path=Path("."))
    return {"ok": True, "restored": snap_id}
