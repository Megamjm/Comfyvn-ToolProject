from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from comfyvn.core.music_stub import pick_mood
router = APIRouter(prefix="/music", tags=["music"])

@router.post("/mood")
def mood(body:dict=Body(...)):
    tags=body.get("tags",[])
    return {"ok":True,"mood":pick_mood(tags)}