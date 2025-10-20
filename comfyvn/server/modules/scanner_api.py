from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/scanner_api.py
# Log Scanner API — parse logs or file tails into structured signals.

from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path

router = APIRouter(prefix="/scanner", tags=["Scanner"])

class ScanLogRequest(BaseModel):
    text: Optional[str] = Field(None, description="Raw log text")
    path: Optional[str] = Field(None, description="Path to a log file")
    tail: int = Field(0, ge=0, le=10000, description="Number of trailing lines to read if path is set")
    patterns: Optional[List[str]] = Field(default=None, description="Simple substring filters to extract")

class ScanLogResponse(BaseModel):
    total_lines: int
    errors: int
    warnings: int
    infos: int
    matches: List[str]
    tail: List[str]

@router.get("/health")
def health():
    return {"ok": True}

@router.post("/scan-log", response_model=ScanLogResponse)
def scan_log(req: ScanLogRequest):
    data: List[str] = []

    if req.text:
        data = req.text.splitlines()
    elif req.path:
        p = Path(req.path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="log file not found")
        try:
            if req.tail > 0:
                from collections import deque
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    dq = deque(f, maxlen=req.tail)
                    data = list(dq)
            else:
                data = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"read error: {e}")
    else:
        data = []

    total = len(data)
    lower = [l.lower() for l in data]
    errors = sum(1 for l in lower if " error" in l or l.startswith("error") or "traceback" in l)
    warnings = sum(1 for l in lower if " warn" in l or l.startswith("warn"))
    infos = sum(1 for l in lower if " info" in l or l.startswith("info"))

    matches: List[str] = []
    if req.patterns:
        pats = [p.lower() for p in req.patterns]
        for line in data:
            ll = line.lower()
            if any(p in ll for p in pats):
                matches.append(line)

    tail = data[-min(len(data), max(0, req.tail)):] if req.tail else (data[-100:] if total > 100 else data)

    return ScanLogResponse(
        total_lines=total,
        errors=errors,
        warnings=warnings,
        infos=infos,
        matches=matches,
        tail=tail,
    )