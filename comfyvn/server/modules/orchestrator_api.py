from PySide6.QtGui import QAction
from fastapi import APIRouter, Body, Request

router = APIRouter()

@router.get("/health")
def health(request: Request):
    orch = getattr(request.app.state, "orchestrator", None)
    return {"ok": bool(orch)}

@router.get("/status")
def status(request: Request):
    orch = getattr(request.app.state, "orchestrator", None)
    return orch.summary() if orch else {"ok": False}

@router.post("/enqueue")
def enqueue(request: Request, payload: dict = Body(...)):
    orch = getattr(request.app.state, "orchestrator", None)
    if not orch:
        return {"ok": False, "error": "no orchestrator"}
    return orch.enqueue(payload)