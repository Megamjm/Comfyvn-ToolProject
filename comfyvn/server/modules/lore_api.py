from PySide6.QtGui import QAction
from fastapi import APIRouter, Body
from comfyvn.core.memory_engine import Lore, remember_event

router = APIRouter()

@router.post("/lore/add")
def add(payload: dict = Body(...)):
    world = payload.get("world","default")
    allw = Lore.get(world, {"entries":[]})
    allw["entries"].append({k:v for k,v in payload.items()})
    Lore.set(world, allw)
    remember_event("lore.add", {"world": world})
    return {"ok": True, "world": world, "count": len(allw["entries"])}

@router.get("/lore/list")
def list_all():
    return {"ok": True, "items": Lore.all()}