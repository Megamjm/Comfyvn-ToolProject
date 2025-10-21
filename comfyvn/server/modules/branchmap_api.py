from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

router = APIRouter(prefix="/branchmap", tags=["branchmap"])


@router.post("/build")
def build(body: dict = Body(...)):
    nodes = []
    for i, step in enumerate(body.get("branches", [])):
        nodes.append(
            {"id": f"n{i}", "choices": len(step) if isinstance(step, list) else 0}
        )
    return {"ok": True, "nodes": nodes, "edges": []}
