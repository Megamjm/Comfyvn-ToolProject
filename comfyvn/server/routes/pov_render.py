from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Body, HTTPException

from comfyvn.pov import POV
from comfyvn.pov.render_pipeline import POVRenderError, POVRenderPipeline

LOGGER = logging.getLogger("comfyvn.api.pov_render")
router = APIRouter(prefix="/api/pov/render", tags=["POV"])
_pipeline = POVRenderPipeline()


def _ensure_mapping(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    raise HTTPException(status_code=400, detail="payload must be an object")


def _extract_style(data: Dict[str, Any]) -> Optional[str]:
    raw = data.get("style")
    if raw is None:
        raw = data.get("variant")
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        return raw or None
    return str(raw)


def _extract_poses(payload: Any) -> Optional[List[str]]:
    if payload is None:
        return None
    if isinstance(payload, str):
        stripped = payload.strip()
        return [stripped] if stripped else None
    if isinstance(payload, Iterable):
        items: List[str] = []
        for item in payload:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items or None
    raise HTTPException(status_code=400, detail="poses must be a string or array")


@router.post("/switch")
async def pov_switch(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload)
    character_raw = data.get("character_id") or data.get("pov")
    if not character_raw or not str(character_raw).strip():
        raise HTTPException(status_code=400, detail="character_id is required")
    character_id = str(character_raw).strip()
    style = _extract_style(data)
    poses = _extract_poses(data.get("poses") or data.get("pose"))
    force = bool(data.get("force", False))
    workflow_hint = data.get("workflow_path") or data.get("workflow")
    extra_meta = data.get("metadata") or data.get("meta")
    if extra_meta is not None and not isinstance(extra_meta, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object")

    state = POV.set(character_id)
    try:
        results = _pipeline.ensure_poses(
            state["pov"],
            style=style,
            poses=poses,
            workflow_path=workflow_hint,
            force=force,
            extra_metadata=extra_meta,
        )
    except POVRenderError as exc:
        LOGGER.warning(
            "POV render rejected char=%s style=%s: %s",
            character_id,
            style or "default",
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("POV render failed char=%s style=%s", character_id, style)
        raise HTTPException(status_code=500, detail="pov render failed") from exc

    return {
        "ok": True,
        "state": state,
        "results": results,
    }
