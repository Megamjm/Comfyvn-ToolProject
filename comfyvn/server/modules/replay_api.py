from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from comfyvn.core.replay import autoplay
router = APIRouter(prefix="/replay", tags=["replay"])

@router.post("/auto")
def auto(body:dict=Body(...)):
    return {"ok":True, **autoplay(body.get("branches",[]), body.get("seed_choice",0))}