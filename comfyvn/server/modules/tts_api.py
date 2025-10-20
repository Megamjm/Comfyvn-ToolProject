from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.core.audio_stub import synth_voice

LOGGER = logging.getLogger("comfyvn.api.tts")
router = APIRouter(prefix="/api/tts", tags=["Audio & Effects"])


class TTSRequest(BaseModel):
    text: str = Field(..., description="Plain text to synthesize")
    voice: str = Field("neutral", description="Voice profile identifier")
    scene_id: Optional[str] = Field(None, description="Optional scene context ID")
    character_id: Optional[str] = Field(None, description="Character voice owner")
    lang: Optional[str] = Field(None, description="Language or locale code")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional client metadata (ignored by stub)",
    )


class TTSResponse(BaseModel):
    ok: bool = True
    artifact: str
    sidecar: Optional[str]
    cached: bool
    voice: str
    lang: str
    info: dict[str, Any] = Field(default_factory=dict)


@router.post("/synthesize", response_model=TTSResponse, summary="Synthesize speech")
def synthesize(payload: TTSRequest = Body(...)) -> TTSResponse:
    LOGGER.debug(
        "TTS request scene=%s character=%s voice=%s lang=%s",
        payload.scene_id,
        payload.character_id,
        payload.voice,
        payload.lang,
    )

    try:
        artifact, sidecar, cached = synth_voice(
            payload.text,
            payload.voice,
            scene_id=payload.scene_id,
            character_id=payload.character_id,
            lang=payload.lang,
        )
    except ValueError as exc:
        LOGGER.warning("Rejected TTS request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed TTS synth")
        raise HTTPException(status_code=500, detail="tts synthesis failed") from exc

    LOGGER.info(
        "TTS artifact=%s cached=%s voice=%s",
        artifact,
        cached,
        payload.voice,
    )

    return TTSResponse(
        artifact=artifact,
        sidecar=sidecar,
        cached=cached,
        voice=payload.voice,
        lang=payload.lang or "default",
        info={"metadata": payload.metadata},
    )
