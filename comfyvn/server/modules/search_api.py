from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from PySide6.QtGui import QAction

from comfyvn.server.core.search_index import (
    INDEX_DIR,
    MANIFEST,
    facets,
    reindex,
    saved_delete,
    saved_get,
    saved_list,
    saved_put,
    search,
)
from comfyvn.server.modules.auth import require_scope

router = APIRouter()


@router.get("/status")
async def status():
    import os
    import time

    try:
        total = 0
        if MANIFEST.exists():
            import json

            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
            total = len((man or {}).get("docs", {}))
        return {
            "ok": True,
            "index_dir": INDEX_DIR.as_posix(),
            "count": total,
            "mtime": (INDEX_DIR.stat().st_mtime if INDEX_DIR.exists() else 0),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/reindex")
async def rebuild(
    body: Dict[str, Any] = None,
    _: bool = Depends(require_scope(["search.write"], cost=5)),
):
    body = body or {}
    full = bool(body.get("full", False))
    try:
        return reindex(full=full)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/query")
async def query(body: Dict[str, Any]):
    try:
        return search(body or {})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/facets")
async def facets_ep(body: Dict[str, Any]):
    q = str((body or {}).get("q") or "")
    try:
        return {"ok": True, "facets": facets(q)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Saved searches
@router.get("/saved/list")
async def saved_list_ep():
    return saved_list()


@router.post("/saved/put/{name}")
async def saved_put_ep(name: str, body: Dict[str, Any]):
    return saved_put(name, body or {})


@router.get("/saved/get/{name}")
async def saved_get_ep(name: str):
    r = saved_get(name)
    if not r.get("ok"):
        raise HTTPException(status_code=404, detail="not found")
    return r


@router.delete("/saved/delete/{name}")
async def saved_delete_ep(name: str):
    return saved_delete(name)
