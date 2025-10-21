from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/meta")
def meta_info():
    return {"ok": True, "version": "5.3", "meta_info_ok": True}


@router.get("/meta/checks")
def meta_checks():
    return {"ok": True, "meta_checks_ok": True}
