from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import wave
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.core.audio_cache import AudioCacheManager
from comfyvn.core.audio_stub import synth_voice
from comfyvn.core.settings_manager import SettingsManager
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


def _resolve_default_lang() -> Optional[str]:
    try:
        settings = SettingsManager()
        cfg = settings.load()
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.debug("Unable to load settings for default lang: %s", exc)
        return None

    audio_cfg = cfg.get("audio", {})
    tts_cfg = audio_cfg.get("tts", {})
    default_lang = tts_cfg.get("default_lang")
    if default_lang:
        return str(default_lang)
    user_cfg = cfg.get("user", {})
    locale_lang = user_cfg.get("language") or user_cfg.get("locale")
    if locale_lang:
        return str(locale_lang)
    return None


def _extract_duration_ms(
    artifact: str, sidecar_payload: dict[str, Any]
) -> Optional[int]:
    raw_seconds = sidecar_payload.get("duration_seconds")
    if raw_seconds is not None:
        try:
            return int(round(float(raw_seconds) * 1000))
        except (TypeError, ValueError):
            LOGGER.debug("Invalid duration_seconds in sidecar: %s", raw_seconds)
    raw_ms = sidecar_payload.get("duration_ms")
    if raw_ms is not None:
        try:
            return int(round(float(raw_ms)))
        except (TypeError, ValueError):
            LOGGER.debug("Invalid duration_ms in sidecar: %s", raw_ms)

    artifact_path = Path(artifact)
    if artifact_path.exists() and artifact_path.suffix.lower() == ".wav":
        try:
            with contextlib.closing(wave.open(str(artifact_path), "rb")) as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate() or 1
                duration = (frames / float(rate)) * 1000.0
                return int(round(duration))
        except wave.Error as exc:
            LOGGER.debug("Failed to read WAV duration for %s: %s", artifact_path, exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug(
                "Unexpected duration read failure for %s: %s", artifact_path, exc
            )
    return None


def _register_tts_asset(
    *,
    artifact: str,
    sidecar: Optional[str],
    sidecar_payload: Optional[dict[str, Any]],
    payload: "TTSRequest",
    cache_key: str,
    text_hash: str,
    cached: bool,
    source: str,
) -> Optional[dict[str, Any]]:
    artifact_path = Path(artifact)
    if not artifact_path.exists():
        LOGGER.warning(
            "TTS artifact missing on disk; skipping asset registration: %s",
            artifact_path,
        )
        return None

    sidecar_payload = sidecar_payload or _load_sidecar(sidecar)
    model_hash = (
        payload.model_hash or payload.model or sidecar_payload.get("model_hash")
    )
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
        "seed": payload.seed,
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
        "seed": payload.seed,
    }
    provenance_payload = {
        "source": source,
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
    model_hash: Optional[str] = Field(
        None, description="Hash of the synthesis model/preset"
    )
    device_hint: Optional[str] = Field(
        None, description="Preferred device id or synthesis target"
    )
    seed: Optional[int] = Field(None, description="Deterministic seed for synthesis")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional client metadata (stored with asset provenance)",
    )


class TTSResponse(BaseModel):
    ok: bool = True
    artifact: str
    sidecar: Optional[str]
    cached: bool
    duration_ms: Optional[int] = Field(
        default=None,
        description="Duration of the synthesized clip in milliseconds when available.",
    )
    voice_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Voice metadata summarising the synthesis request.",
    )
    asset_id: Optional[str] = Field(
        default=None, description="Registered asset identifier when available."
    )
    voice: str
    lang: str
    style: Optional[str]
    asset: Optional[dict[str, Any]] = Field(
        default=None,
        description="Asset registry entry for the synthesized clip, when registration succeeds.",
    )
    info: dict[str, Any] = Field(default_factory=dict)


def _handle_tts_request(payload: TTSRequest, *, source_route: str) -> TTSResponse:
    cleaned_text = payload.text.strip()
    if not cleaned_text:
        LOGGER.warning("Rejected TTS request: empty text after trimming")
        raise HTTPException(status_code=400, detail="text must not be empty")

    resolved_lang = payload.lang or _resolve_default_lang()
    if resolved_lang and payload.lang != resolved_lang:
        payload.lang = resolved_lang

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
        "TTS request scene=%s line=%s character=%s voice=%s lang=%s style=%s device=%s cache_key=%s seed=%s",
        payload.scene_id,
        payload.line_id,
        payload.character_id,
        payload.voice,
        payload.lang,
        payload.style,
        payload.device_hint,
        cache_key,
        payload.seed,
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
            seed=payload.seed,
        )
    except ValueError as exc:
        LOGGER.warning("Rejected TTS request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed TTS synth")
        raise HTTPException(status_code=500, detail="tts synthesis failed") from exc

    sidecar_payload = _load_sidecar(sidecar)
    duration_ms = _extract_duration_ms(artifact, sidecar_payload)

    asset_info = _register_tts_asset(
        artifact=artifact,
        sidecar=sidecar,
        sidecar_payload=sidecar_payload,
        payload=payload,
        cache_key=cache_key,
        text_hash=text_hash,
        cached=cached,
        source=source_route,
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
        "seed": payload.seed,
        "route": source_route,
    }
    if duration_ms is not None:
        info_payload["duration_ms"] = duration_ms
    if asset_info:
        info_payload["asset_uid"] = asset_info["uid"]

    voice_meta = {
        "voice": sidecar_payload.get("voice") or payload.voice,
        "style": sidecar_payload.get("style") or payload.style or "default",
        "lang": sidecar_payload.get("lang") or payload.lang or "default",
        "model": sidecar_payload.get("model") or payload.model,
        "model_hash": sidecar_payload.get("model_hash") or payload.model_hash,
        "character_id": payload.character_id,
        "scene_id": payload.scene_id,
        "provider": sidecar_payload.get("provider"),
        "device_hint": sidecar_payload.get("device_hint") or payload.device_hint,
        "seed": sidecar_payload.get("seed") or payload.seed,
        "cached": cached,
    }
    voice_meta = {key: value for key, value in voice_meta.items() if value is not None}

    return TTSResponse(
        artifact=artifact,
        sidecar=sidecar,
        cached=cached,
        duration_ms=duration_ms,
        voice_meta=voice_meta,
        asset_id=asset_info["uid"] if asset_info else None,
        voice=payload.voice,
        lang=payload.lang or "default",
        style=payload.style,
        asset=asset_info,
        info=info_payload,
    )


@router.post(
    "/speak", response_model=TTSResponse, summary="Character-aware speech synthesis"
)
def speak(payload: TTSRequest = Body(...)) -> TTSResponse:
    return _handle_tts_request(payload, source_route="api.tts.speak")


@router.post("/synthesize", response_model=TTSResponse, summary="Synthesize speech")
def synthesize(payload: TTSRequest = Body(...)) -> TTSResponse:
    return _handle_tts_request(payload, source_route="api.tts.synthesize")
