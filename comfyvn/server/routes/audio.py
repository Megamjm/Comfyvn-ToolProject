from __future__ import annotations

"""
Audio lab routes exposing stubbed TTS and music remix functionality.

These endpoints provide deterministic outputs backed by lightweight cache
adapters so the GUI can iterate on workflows before real synthesis lands.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from comfyvn.bridge.music_adapter import remix
from comfyvn.bridge.tts_adapter import synthesize

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Audio"])


def _expect_dict(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    return payload


@router.post("/tts/speak")
async def tts_speak(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _expect_dict(payload)

    character = str(data.get("character") or "narrator")
    text = str(data.get("text") or "")
    style = str(data.get("style") or "neutral")
    model = str(data.get("model") or "xtts")
    seed = data.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="seed must be numeric"
            ) from None

    LOGGER.info(
        "TTS speak request character=%s model=%s style=%s seed=%s text_len=%d",
        character,
        model,
        style,
        seed,
        len(text),
    )

    result = synthesize(
        character,
        text,
        style,
        model,
        seed=seed,
    )
    return {"ok": True, "data": result}


@router.post("/music/remix")
async def music_remix(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _expect_dict(payload)

    track_path = str(data.get("track") or "")
    style = str(data.get("style") or "ambient")

    LOGGER.info("Music remix request track=%s style=%s", track_path, style)
    result = remix(track_path, style)
    return {"ok": True, "data": result}
