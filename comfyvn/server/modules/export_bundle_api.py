from PySide6.QtGui import QAction
# comfyvn/server/modules/export_bundle_api.py
from fastapi import APIRouter
from pathlib import Path
import shutil, time

router = APIRouter()
REN = Path("exports/renpy")
BUNDLES = Path("exports/bundles")
REN.mkdir(parents=True, exist_ok=True)
BUNDLES.mkdir(parents=True, exist_ok=True)

@router.get("/health")
def health():
    return {"ok": True, "renpy_exists": REN.exists()}

@router.post("/bundle/renpy")
def bundle_renpy():
    ts = int(time.time())
    base = BUNDLES / f"renpy_{ts}"
    # shutil.make_archive adds extension automatically for format="zip"
    shutil.make_archive(str(base), "zip", REN)
    zip_path = str(base) + ".zip"
    return {"ok": True, "zip": zip_path}