from PySide6.QtGui import QAction

# comfyvn/server/modules/playground_api.py
from fastapi import APIRouter
from pathlib import Path

router = APIRouter()
PRJ = Path("data/playground")

@router.get("/health")
def health():
    ok = PRJ.exists()
    return {"ok": True, "engine": "godot", "project_dir": str(PRJ), "present": ok}

@router.get("/recommend")
def recommend():
    return {"ok": True, "engines": [
        {"name": "Godot", "why": "Open-source, lightweight 3D/2D, good for preview"},
        {"name": "Blend4Web/Three.js", "why": "Web preview alternative"}
    ]}