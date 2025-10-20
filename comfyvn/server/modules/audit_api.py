from __future__ import annotations
from PySide6.QtGui import QAction
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
import time, json
from comfyvn.server.modules.auth import require_scope
from comfyvn.server.core.audit import export_range, verify_range, AUDIT_DIR

router = APIRouter()

@router.get("/status")
async def status():
    try:
        p = sorted(AUDIT_DIR.glob("*.jsonl"))[-1] if list(AUDIT_DIR.glob("*.jsonl")) else None
        return {"ok": True, "latest": p.name if p else None, "size": (p.stat().st_size if p else 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/export")
async def export(start: float, end: float, _: bool = Depends(require_scope(["*"]))):
    if end < start: raise HTTPException(400, "bad range")
    text = export_range(start, end)
    return {"ok": True, "ndjson": text}

@router.get("/verify")
async def verify(start: float, end: float, _: bool = Depends(require_scope(["*"]))):
    if end < start: raise HTTPException(400, "bad range")
    return verify_range(start, end)