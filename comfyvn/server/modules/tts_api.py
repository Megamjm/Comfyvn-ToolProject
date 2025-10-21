from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.core.audio_cache import AudioCacheManager
from comfyvn.core.audio_stub import synth_voice
from comfyvn.studio.core import AssetRegistry

LOGGER = logging.getLogger("comfyvn.api.tts")
router = APIRouter(prefix="/api/tts", tags=["Audio & Effects"])

_ASSET_REGISTRY = AssetRegistry()


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _load_sidecar(sidecar: Optional[str]) -> dict[str, Any]:
    if not sidecar:
        return {}
    try:
        return json.loads(Path(sidecar).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Unable to read TTS sidecar %s: %s", sidecar, exc)
        return {}


def _register_tts_asset(
    *,
    artifact: str,
    sidecar: Optional[str],
    payload: "TTSRequest",
    cache_key: str,
    text_hash: str,
    cached: bool,
) -> Optional[dict[str, Any]]:
    artifact_path = Path(artifact)
    if not artifact_path.exists():
        LOGGER.warning("TTS artifact missing on disk; skipping asset registration: %s", artifact_path)
        return None

    sidecar_payload = _load_sidecar(sidecar)
    model_hash = payload.model_hash or payload.model or sidecar_payload.get("model_hash")
    asset_metadata: dict[str, Any] = {
        "scene_id": payload.scene_id,
        "line_id": payload.line_id,
        "character_id": payload.character_id,
        "voice": payload.voice,
        "style": payload.style or "default",
        "lang": payload.lang or "default",
        "model_hash": model_hash,
        "device_hint": payload.device_hint,
        "text_hash": text_hash,
        "cache_key": cache_key,
        "cached": cached,
        "sidecar": sidecar,
        "export_path": str(artifact_path),
    }
    if payload.metadata:
        asset_metadata["request_meta"] = dict(payload.metadata)
    if sidecar_payload:
        asset_metadata["synth"] = {
            "provider": sidecar_payload.get("provider"),
            "created_at": sidecar_payload.get("created_at"),
            "duration_seconds": sidecar_payload.get("duration_seconds"),
            "sample_rate": sidecar_payload.get("sample_rate"),
        }

    provenance_inputs = {
        "scene_id": payload.scene_id,
        "line_id": payload.line_id,
        "character_id": payload.character_id,
        "voice": payload.voice,
        "style": payload.style or "default",
        "lang": payload.lang or "default",
        "model_hash": model_hash,
        "device_hint": payload.device_hint,
        "text_hash": text_hash,
        "cache_key": cache_key,
        "cached": cached,
        "text_length": len(payload.text.strip()),
    }
    provenance_payload = {
        "source": "api.tts.synthesize",
        "inputs": provenance_inputs,
        "user_id": (payload.metadata or {}).get("user_id"),
    }
    license_tag = (payload.metadata or {}).get("license")

    dest_relative = Path("audio/voice") / artifact_path.name
    try:
        asset_info = _ASSET_REGISTRY.register_file(
            artifact_path,
            asset_type="audio.voice",
            dest_relative=dest_relative,
            metadata=asset_metadata,
            copy=True,
            provenance=provenance_payload,
            license_tag=license_tag,
        )
        LOGGER.info(
            "TTS asset registered uid=%s scene=%s character=%s line=%s",
            asset_info["uid"],
            payload.scene_id,
            payload.character_id,
            payload.line_id,
        )
        return asset_info
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Failed to register TTS asset %s: %s", artifact_path, exc)
        return None


class TTSRequest(BaseModel):
    text: str = Field(..., description="Plain text to synthesize")
    voice: str = Field("neutral", description="Voice profile identifier")
    scene_id: Optional[str] = Field(None, description="Optional scene context ID")
    line_id: Optional[str] = Field(None, description="Optional scene line identifier")
    character_id: Optional[str] = Field(None, description="Character voice owner")
    lang: Optional[str] = Field(None, description="Language or locale code")
    style: Optional[str] = Field(None, description="Optional vocal styling or preset")
    model: Optional[str] = Field(None, description="Engine or pipeline identifier")
    model_hash: Optional[str] = Field(None, description="Hash of the synthesis model/preset")
    device_hint: Optional[str] = Field(None, description="Preferred device id or synthesis target")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional client metadata (stored with asset provenance)",
    )


class TTSResponse(BaseModel):
    ok: bool = True
    artifact: str
    sidecar: Optional[str]
    cached: bool
    voice: str
    lang: str
    style: Optional[str]
    asset: Optional[dict[str, Any]] = Field(
        default=None,
        description="Asset registry entry for the synthesized clip, when registration succeeds.",
    )
    info: dict[str, Any] = Field(default_factory=dict)


@router.post("/synthesize", response_model=TTSResponse, summary="Synthesize speech")
def synthesize(payload: TTSRequest = Body(...)) -> TTSResponse:
    cleaned_text = payload.text.strip()
    if not cleaned_text:
        LOGGER.warning("Rejected TTS request: empty text after trimming")
        raise HTTPException(status_code=400, detail="text must not be empty")

    text_hash = _hash_text(cleaned_text)
    model_hash = payload.model_hash or payload.model
    cache_key = AudioCacheManager.make_key(
        character_id=payload.character_id,
        text_hash=text_hash,
        voice=payload.voice,
        style=payload.style,
        lang=payload.lang,
        model_hash=model_hash,
    )

    LOGGER.debug(
        "TTS request scene=%s line=%s character=%s voice=%s lang=%s style=%s device=%s cache_key=%s",
        payload.scene_id,
        payload.line_id,
        payload.character_id,
        payload.voice,
        payload.lang,
        payload.style,
        payload.device_hint,
        cache_key,
    )

    try:
        artifact, sidecar, cached = synth_voice(
            payload.text,
            payload.voice,
            scene_id=payload.scene_id,
            character_id=payload.character_id,
            lang=payload.lang,
            style=payload.style,
            model_hash=model_hash,
            device_hint=payload.device_hint,
        )
    except ValueError as exc:
        LOGGER.warning("Rejected TTS request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed TTS synth")
        raise HTTPException(status_code=500, detail="tts synthesis failed") from exc

    asset_info = _register_tts_asset(
        artifact=artifact,
        sidecar=sidecar,
        payload=payload,
        cache_key=cache_key,
        text_hash=text_hash,
        cached=cached,
    )

    LOGGER.info(
        "TTS artifact=%s cached=%s voice=%s style=%s asset=%s",
        artifact,
        cached,
        payload.voice,
        payload.style or "default",
        asset_info["uid"] if asset_info else None,
    )

    info_meta = dict(payload.metadata or {})
    if payload.model:
        info_meta.setdefault("model", payload.model)
    if payload.model_hash:
        info_meta.setdefault("model_hash", payload.model_hash)

    info_payload = {
        "metadata": info_meta,
        "scene_id": payload.scene_id,
        "line_id": payload.line_id,
        "character_id": payload.character_id,
        "device_hint": payload.device_hint,
        "cache_key": cache_key,
        "text_hash": text_hash,
    }
    if asset_info:
        info_payload["asset_uid"] = asset_info["uid"]

    return TTSResponse(
        artifact=artifact,
        sidecar=sidecar,
        cached=cached,
        voice=payload.voice,
        lang=payload.lang or "default",
        style=payload.style,
        asset=asset_info,
        info=info_payload,
    )
