from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from comfyvn.core.analyzers import continuity_check
router = APIRouter(prefix="/continuity", tags=["continuity"])

@router.post("/validate")
def validate(body:dict=Body(...)):
    return continuity_check(body.get("states",[]))