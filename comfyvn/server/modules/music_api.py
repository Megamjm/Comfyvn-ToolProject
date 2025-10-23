from __future__ import annotations

import contextlib
import logging
import wave
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.core.music_remix import remix_track
from comfyvn.studio.core import AssetRegistry

LOGGER = logging.getLogger("comfyvn.api.music")
router = APIRouter(prefix="/api/music", tags=["Audio & Effects"])

_ASSET_REGISTRY = AssetRegistry()


def _extract_duration_ms(artifact: str, metadata: dict[str, Any]) -> Optional[int]:
    raw_seconds = metadata.get("duration_seconds")
    if raw_seconds is not None:
        try:
            return int(round(float(raw_seconds) * 1000))
        except (TypeError, ValueError):
            LOGGER.debug("Invalid duration_seconds in music metadata: %s", raw_seconds)

    artifact_path = Path(artifact)
    if artifact_path.exists() and artifact_path.suffix.lower() == ".wav":
        try:
            with contextlib.closing(wave.open(str(artifact_path), "rb")) as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate() or 1
                return int(round((frames / float(rate)) * 1000))
        except wave.Error as exc:
            LOGGER.debug("Failed to read WAV duration for remix %s: %s", artifact, exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug(
                "Unexpected duration read failure for remix %s: %s", artifact, exc
            )
    return None


def _register_music_asset(
    *,
    artifact: str,
    sidecar: Optional[str],
    metadata: dict[str, Any],
    scene_id: str,
    style: str,
    cached: bool,
) -> Optional[dict[str, Any]]:
    artifact_path = Path(artifact)
    if not artifact_path.exists():
        LOGGER.warning(
            "Music artifact missing on disk; skipping asset registration: %s",
            artifact_path,
        )
        return None

    asset_metadata: dict[str, Any] = {
        "scene_id": scene_id,
        "style": style,
        "mood_tags": metadata.get("mood_tags") or [],
        "seed": metadata.get("seed"),
        "provider": metadata.get("provider"),
        "cache_key": metadata.get("cache_key"),
        "cached": cached,
        "duration_seconds": metadata.get("duration_seconds"),
        "tempo": metadata.get("tempo"),
        "sidecar": sidecar,
        "source_track": metadata.get("source_track"),
    }
    if "layers" in metadata:
        asset_metadata["layers"] = metadata["layers"]
    asset_metadata["remix_meta"] = dict(metadata)

    provenance_inputs = {
        "scene_id": scene_id,
        "style": style,
        "mood_tags": metadata.get("mood_tags") or [],
        "seed": metadata.get("seed"),
        "cache_key": metadata.get("cache_key"),
        "provider": metadata.get("provider"),
        "cached": cached,
    }
    provenance_payload = {
        "source": "api.music.remix",
        "inputs": provenance_inputs,
    }
    license_tag = metadata.get("license")

    dest_relative = Path("audio/music") / artifact_path.name
    try:
        asset_info = _ASSET_REGISTRY.register_file(
            artifact_path,
            asset_type="audio.music",
            dest_relative=dest_relative,
            metadata=asset_metadata,
            copy=True,
            provenance=provenance_payload,
            license_tag=license_tag,
        )
        LOGGER.info(
            "Music asset registered uid=%s scene=%s style=%s",
            asset_info["uid"],
            scene_id,
            style,
        )
        return asset_info
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Failed to register music asset %s: %s", artifact_path, exc)
        return None


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
    asset_id: Optional[str] = None
    artifact: str
    sidecar: Optional[str]
    style: str
    cached: bool
    duration_ms: Optional[int] = Field(
        default=None,
        description="Duration in milliseconds when determinable.",
    )
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

    try:
        artifact, sidecar, cached, metadata = remix_track(
            scene_id=scene,
            target_style=style,
            source_track=payload.source_track,
            seed=payload.seed,
            mood_tags=payload.mood_tags,
        )
    except Exception as exc:
        LOGGER.exception("Music remix stub failed: %s", exc)
        raise HTTPException(status_code=500, detail="music remix failed") from exc

    duration_ms = _extract_duration_ms(artifact, metadata)
    asset_info = _register_music_asset(
        artifact=artifact,
        sidecar=sidecar,
        metadata=metadata,
        scene_id=scene,
        style=style,
        cached=cached,
    )

    info_payload: dict[str, Any] = {
        "scene_id": scene,
        "target_style": style,
        "source_track": payload.source_track,
        "seed": payload.seed,
        "mood_tags": payload.mood_tags,
        "cache_key": metadata.get("cache_key"),
        "provider": metadata.get("provider"),
        "cached": cached,
    }
    if duration_ms is not None:
        info_payload["duration_ms"] = duration_ms
    if asset_info:
        info_payload["asset_uid"] = asset_info["uid"]

    LOGGER.info(
        "Music remix artifact=%s cached=%s scene=%s style=%s asset=%s",
        artifact,
        cached,
        scene,
        style,
        asset_info["uid"] if asset_info else None,
    )
    return RemixResponse(
        asset_id=asset_info["uid"] if asset_info else None,
        artifact=artifact,
        sidecar=sidecar,
        style=style,
        cached=cached,
        duration_ms=duration_ms,
        info=info_payload,
    )
