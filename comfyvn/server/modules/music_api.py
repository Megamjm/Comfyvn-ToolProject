from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.core.music_remix import remix_track

LOGGER = logging.getLogger("comfyvn.api.music")
router = APIRouter(prefix="/api/music", tags=["Audio & Effects"])


class RemixRequest(BaseModel):
    scene_id: str = Field(..., description="Scene identifier to align the remix with")
    target_style: str = Field(..., description="Desired music style or mood label")
    source_track: Optional[str] = Field(None, description="Existing track to remix from")
    seed: Optional[int] = Field(None, description="Deterministic seed for remix pipeline")
    mood_tags: List[str] = Field(default_factory=list, description="Optional mood hints")


class RemixResponse(BaseModel):
    ok: bool = True
    artifact: str
    sidecar: str
    info: dict = Field(default_factory=dict)


@router.post("/remix", response_model=RemixResponse, summary="Generate a music remix stub")
def remix(payload: RemixRequest = Body(...)) -> RemixResponse:
    scene = payload.scene_id.strip()
    style = payload.target_style.strip()
    if not scene or not style:
        LOGGER.warning("Music remix rejected: scene/style required")
        raise HTTPException(status_code=400, detail="scene_id and target_style are required")

    artifact, sidecar = remix_track(
        scene_id=scene,
        target_style=style,
        source_track=payload.source_track,
        seed=payload.seed,
        mood_tags=payload.mood_tags,
    )
    LOGGER.info(
        "Music remix artifact=%s scene=%s style=%s",
        artifact,
        scene,
        style,
    )
    return RemixResponse(
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
