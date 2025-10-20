from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.scene_bundle import build_bundle, ASSETS_MANIFEST_DEFAULT, SCHEMA_PATH_DEFAULT

router = APIRouter(prefix="/api/studio", tags=["Studio"])
logger = logging.getLogger(__name__)

STATE: Dict[str, Any] = {
    "project_id": "default",
    "view": "Modules",
}


def _load_json(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load JSON from %s: %s", path, exc)
        return None


@router.post("/open_project")
async def open_project(payload: Dict[str, Any]) -> Dict[str, Any]:
    project_id = (payload.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    STATE["project_id"] = project_id
    logger.info("Studio project opened: %s", project_id)
    return {"ok": True, "project_id": project_id}


@router.post("/switch_view")
async def switch_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    view = (payload.get("view") or "").strip()
    if not view:
        raise HTTPException(status_code=400, detail="view is required")
    STATE["view"] = view
    logger.info("Studio view switched to: %s", view)
    return {"ok": True, "view": view}


@router.post("/export_bundle")
async def export_bundle(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("raw")
    raw_path = payload.get("raw_path")
    if not raw and not raw_path:
        raise HTTPException(status_code=400, detail="raw or raw_path is required")

    if raw_path and not raw:
        raw = _load_json(raw_path)
        if raw is None:
            raise HTTPException(status_code=400, detail="raw_path does not exist or is invalid")

    manifest_path = payload.get("manifest_path", ASSETS_MANIFEST_DEFAULT)
    schema_path = payload.get("schema_path", SCHEMA_PATH_DEFAULT)
    manifest = _load_json(manifest_path)

    try:
        bundle = build_bundle(raw, manifest, schema_path=schema_path)
    except Exception as exc:
        logger.error("Bundle export failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"bundle export failed: {exc}") from exc

    out_path_value = payload.get("out_path")
    if out_path_value:
        out_path = Path(out_path_value)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Bundle exported to %s", out_path)
        response_bundle: Any = {"path": str(out_path)}
    else:
        response_bundle = bundle
        logger.info("Bundle generated (not written to disk) for project %s", STATE["project_id"])

    return {"ok": True, "bundle": response_bundle}
