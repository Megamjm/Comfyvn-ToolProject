from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
router = APIRouter(prefix="/branchmap", tags=["branchmap"])

@router.post("/build")
def build(body:dict=Body(...)):
    nodes = []
    for i,step in enumerate(body.get("branches",[])):
        nodes.append({"id":f"n{i}", "choices": len(step) if isinstance(step,list) else 0})
    return {"ok":True,"nodes":nodes,"edges":[]}