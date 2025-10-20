from PySide6.QtGui import QAction
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from .parser import RoleplayParser
from .formatter import RoleplayFormatter
router = APIRouter()
@router.post('/import')
async def import_roleplay(file: UploadFile = File(...), world: Optional[str] = Form(None), source: Optional[str] = Form('upload')):
    try:
        raw=(await file.read()).decode('utf-8', errors='replace'); lines=RoleplayParser().parse_text(raw); scene=RoleplayFormatter().to_scene(lines, world=world, source=source)
        return JSONResponse({"ok": True, "scene": scene})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")