from PySide6.QtGui import QAction

from fastapi import APIRouter

router = APIRouter(prefix="/gui", tags=["gui"])
@router.get("/config")
def gui_config():
    return {
        "ok": True,
        "studio": {"path": "/studio/"},
        "bridges": {
            "sillytavern": {"url": "http://localhost:8000"},
            "comfyui": {"url": "http://localhost:8188"},
            "lmstudio": {"url": "http://localhost:1234"},
        },
    }