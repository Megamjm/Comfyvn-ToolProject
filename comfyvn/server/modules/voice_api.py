from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from comfyvn.core.audio_stub import synth_voice
from comfyvn.core.memory_engine import Voices, remember_event

LOGGER = logging.getLogger("comfyvn.api.voice")
router = APIRouter(tags=["Audio & Effects"])


@router.get("/voice/list")
def list_voices() -> Dict[str, Any]:
    items = Voices.all()
    LOGGER.debug("Voice profiles listed count=%s", len(items))
    return {"ok": True, "items": items}


@router.post("/voice/profile")
def set_profile(payload: dict = Body(...)) -> Dict[str, Any]:
    name = payload.get("name", "default")
    Voices.set(name, payload)
    remember_event("voice.profile", {"name": name})
    LOGGER.info("Voice profile set name=%s", name)
    return {"ok": True, "name": name}


@router.post("/voice/speak")
def speak(payload: dict = Body(...)) -> Dict[str, Any]:
    text = (payload.get("text") or "").strip()
    if not text:
        LOGGER.warning("Voice speak rejected: empty text")
        raise HTTPException(status_code=400, detail="text must not be empty")

    voice = payload.get("voice", "default")
    lang = payload.get("lang")
    scene_id = payload.get("scene_id")
    character_id = payload.get("character_id")

    try:
        artifact, sidecar, cached = synth_voice(
            text,
            voice,
            scene_id=scene_id,
            character_id=character_id,
            lang=lang,
        )
    except ValueError as exc:
        LOGGER.warning("Voice speak rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Voice speak failed")
        raise HTTPException(status_code=500, detail="voice synth failed") from exc

    remember_event(
        "voice.speak",
        {
            "voice": voice,
            "scene_id": scene_id,
            "character_id": character_id,
            "artifact": artifact,
            "cached": cached,
        },
    )
    LOGGER.info(
        "Voice synth voice=%s cached=%s artifact=%s",
        voice,
        cached,
        artifact,
    )
    return {
        "ok": True,
        "voice": voice,
        "text": text,
        "artifact": artifact,
        "sidecar": sidecar,
        "cached": cached,
    }
