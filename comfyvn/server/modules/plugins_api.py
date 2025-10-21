from __future__ import annotations

from fastapi import APIRouter
from PySide6.QtGui import QAction

from comfyvn.ext.plugins import PluginManager

router = APIRouter()


@router.get("/list")
async def list_plugins():
    pm = PluginManager()
    items = []
    for name, plug in pm.plugins.items():
        items.append(
            {
                "name": name,
                "jobs": list(plug.jobs.keys()),
                "meta": getattr(plug, "meta", {}),
            }
        )
    return {"ok": True, "items": items}
