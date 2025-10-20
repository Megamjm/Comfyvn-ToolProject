from PySide6.QtGui import QAction
from fastapi import APIRouter, Body, HTTPException
from comfyvn.core.memory_engine import Personas, remember_event

router = APIRouter()

@router.post("/persona/set")
def set_persona(payload: dict = Body(...)):
    name = payload.get("name")
    if not name: raise HTTPException(400, "name required")
    rec = Personas.get(name, {}) | {k:v for k,v in payload.items() if k!="name"}
    Personas.set(name, rec)
    remember_event("persona.set", {"name": name})
    return {"ok": True, "name": name, "data": rec}

@router.get("/persona/get/{name}")
def get_persona(name: str):
    rec = Personas.get(name)
    if not rec: raise HTTPException(404, "not found")
    return {"ok": True, "name": name, "data": rec}

@router.post("/persona/inherit")
def inherit(payload: dict = Body(...)):
    parent = payload.get("parent"); child = payload.get("child")
    if not parent or not child: raise HTTPException(400, "parent and child required")
    base = Personas.get(parent, {})
    override = payload.get("override", {})
    Personas.set(child, base | override)
    remember_event("persona.inherit", {"parent": parent, "child": child})
    return {"ok": True, "child": child, "data": Personas.get(child)}

@router.get("/persona/list")
def list_all():
    return {"ok": True, "items": Personas.all()}