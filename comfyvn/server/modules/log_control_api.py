# comfyvn/server/modules/log_control_api.py
import logging

from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

router = APIRouter(prefix="/log", tags=["log"])


@router.post("/level")
def set_level(body: dict = Body(...)):
    lvl = str(body.get("level", "INFO")).upper()
    logging.getLogger().setLevel(getattr(logging, lvl, logging.INFO))
    return {"ok": True, "level": lvl}
