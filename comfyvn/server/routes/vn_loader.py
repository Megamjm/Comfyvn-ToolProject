# Phase 2/2 Project Integration Chat — VN loader routes
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from comfyvn.vn.loader import BuildError, build_project

router = APIRouter(prefix="/api/vn", tags=["vn"])
log = logging.getLogger(__name__)

PROJECTS_ROOT = Path("data/projects")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON at %s: %s", path, exc)
        raise HTTPException(status_code=500, detail=f"Invalid JSON at {path.name}")


@router.get("/projects")
def list_projects() -> Dict[str, Any]:
    items = []
    if PROJECTS_ROOT.exists():
        for proj in sorted(PROJECTS_ROOT.iterdir()):
            if not proj.is_dir():
                continue
            manifest = _read_json(proj / "manifest.json") or {
                "projectId": proj.name,
                "sceneCount": 0,
                "personaCount": 0,
                "assetCount": 0,
            }
            items.append(manifest)
    return {"items": items}


@router.post("/build")
def build_vn(payload: Dict[str, Any]) -> Dict[str, Any]:
    project_id = (payload.get("projectId") or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required")

    sources = payload.get("sources") or []
    if not isinstance(sources, list):
        raise HTTPException(status_code=400, detail="sources must be an array")

    workspace = payload.get("workspace") or "."
    base_dir = Path(workspace).resolve()
    options = payload.get("options") or {}

    if not base_dir.exists():
        raise HTTPException(status_code=400, detail="workspace path does not exist")
    if not base_dir.is_dir():
        raise HTTPException(status_code=400, detail="workspace must be a directory")

    try:
        result = build_project(project_id, sources, base_dir, options=options)
    except BuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("VN build failed for %s", project_id)
        raise HTTPException(status_code=500, detail="VN build failed") from exc

    return result


@router.get("/scenes")
def list_scenes(
    projectId: str = Query(alias="projectId"),
    sceneId: Optional[str] = Query(default=None, alias="sceneId"),
    includeManifest: bool = Query(default=False, alias="includeManifest"),
) -> Dict[str, Any]:
    project_id = (projectId or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required")

    project_dir = PROJECTS_ROOT / project_id
    scenes_dir = project_dir / "scenes"
    if not scenes_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    items = []
    for file in sorted(scenes_dir.glob("*.json")):
        data = _read_json(file)
        if not data:
            continue
        if sceneId and data.get("id") != sceneId:
            continue
        items.append(data)

    response: Dict[str, Any] = {"items": items}
    if includeManifest:
        response["manifest"] = _read_json(project_dir / "manifest.json")
    return response
