from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.core.music_remix import remix_track
from comfyvn.core.task_registry import task_registry

LOGGER = logging.getLogger("comfyvn.api.music")
router = APIRouter(prefix="/api/music", tags=["Audio & Effects"])


class RemixRequest(BaseModel):
    scene_id: str = Field(..., description="Scene identifier to align the remix with")
    target_style: str = Field(..., description="Desired music style or mood label")
    source_track: Optional[str] = Field(
        None, description="Existing track to remix from"
    )
    seed: Optional[int] = Field(
        None, description="Deterministic seed for remix pipeline"
    )
    mood_tags: List[str] = Field(
        default_factory=list, description="Optional mood hints"
    )


class RemixResponse(BaseModel):
    ok: bool = True
    job_id: str
    status: str
    artifact: Optional[str] = None
    sidecar: Optional[str] = None
    info: dict = Field(default_factory=dict)


@router.post(
    "/remix", response_model=RemixResponse, summary="Generate a music remix stub"
)
def remix(payload: RemixRequest = Body(...)) -> RemixResponse:
    scene = payload.scene_id.strip()
    style = payload.target_style.strip()
    if not scene or not style:
        LOGGER.warning("Music remix rejected: scene/style required")
        raise HTTPException(
            status_code=400, detail="scene_id and target_style are required"
        )

    job_payload = {
        "scene_id": scene,
        "target_style": style,
        "source_track": payload.source_track,
        "seed": payload.seed,
        "mood_tags": payload.mood_tags,
    }
    job_id = task_registry.register(
        "audio.music.remix",
        job_payload,
        message=f"music remix {scene} → {style}",
        meta={"origin": "api.music.remix"},
    )

    task_registry.update(
        job_id, status="running", progress=0.2, message="remix stub running"
    )

    artifact: Optional[str] = None
    sidecar: Optional[str] = None
    try:
        artifact, sidecar = remix_track(
            scene_id=scene,
            target_style=style,
            source_track=payload.source_track,
            seed=payload.seed,
            mood_tags=payload.mood_tags,
        )
    except Exception as exc:
        LOGGER.exception("Music remix stub failed: %s", exc)
        task_registry.update(job_id, status="error", message=str(exc))
        raise HTTPException(status_code=500, detail="music remix failed") from exc

    job = task_registry.get(job_id)
    meta_snapshot = dict((job.meta if job else {}) or {})
    result_meta = dict(meta_snapshot.get("result") or {})
    if artifact:
        result_meta["artifact"] = artifact
    if sidecar:
        result_meta["sidecar"] = sidecar
    meta_snapshot["result"] = result_meta
    task_registry.update(
        job_id, status="done", progress=1.0, message="remix ready", meta=meta_snapshot
    )

    LOGGER.info(
        "Music remix artifact=%s scene=%s style=%s job_id=%s",
        artifact,
        scene,
        style,
        job_id,
    )
    return RemixResponse(
        job_id=job_id,
        status="done",
        artifact=artifact,
        sidecar=sidecar,
        info={
            "scene_id": scene,
            "target_style": style,
            "source_track": payload.source_track,
            "seed": payload.seed,
            "mood_tags": payload.mood_tags,
        },
    )
