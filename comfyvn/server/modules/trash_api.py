from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Depends
from comfyvn.server.core.trash import list_trash, restore, purge
from comfyvn.server.modules.auth import require_scope

router = APIRouter()

@router.get("/list")
async def list_trash_items(limit: int = 200):
    return {"ok": True, "items": list_trash(limit)}

@router.post("/restore/{name}")
async def restore_item(name: str, _: bool = Depends(require_scope(["content.write"]))):
    return {"ok": restore(name)}

@router.delete("/purge/{name}")
async def purge_item(name: str, _: bool = Depends(require_scope(["content.write"]))):
    return {"ok": purge(name)}