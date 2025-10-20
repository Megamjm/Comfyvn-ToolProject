from PySide6.QtGui import QAction

from fastapi import APIRouter
from comfyvn.core.plugin_loader import PluginLoader

router = APIRouter(prefix="/plugins", tags=["plugins"])
PL = PluginLoader()

@router.get("/list")
def list_plugins(): return {"ok": True, "items": PL.list()}

@router.post("/reload")
def reload_plugins(): return {"ok": True, "loaded": PL.import_all()}