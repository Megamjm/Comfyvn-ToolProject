from PySide6.QtGui import QAction

# comfyvn/server/modules/control_api.py
from fastapi import APIRouter, Body
from typing import Dict, Any

router = APIRouter()
_state = {"active_character": None}

@router.get("/who")
def who(): return {"ok": True, "active_character": _state["active_character"]}

@router.post("/swap")
def swap(body: Dict[str,Any] = Body(...)):
    name = body.get("name")
    _state["active_character"] = name
    return {"ok": True, "active_character": name}