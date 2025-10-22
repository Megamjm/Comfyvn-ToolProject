from __future__ import annotations

"""
Audio lab routes exposing stubbed TTS and music remix functionality.

These endpoints provide deterministic outputs backed by lightweight cache
adapters so the GUI can iterate on workflows before real synthesis lands.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, HTTPException

from comfyvn.audio.alignment import (
    align_text,
    alignment_to_lipsync_payload,
    write_alignment,
)
from comfyvn.audio.mixer import DuckingConfig, TrackSpec, mix_tracks
from comfyvn.bridge.music_adapter import remix
from comfyvn.bridge.tts_adapter import synthesize

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Audio"])

_MIX_ROOT = Path("data/audio/mixes")


def _expect_dict(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    return payload


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed loading JSON %s: %s", path, exc)
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sanitize_roles(values: Sequence[Any], *, default: Sequence[str]) -> List[str]:
    if not values:
        return [str(item) for item in default]
    result = []
    for value in values:
        if value is None:
            continue
        result.append(str(value))
    return result or [str(item) for item in default]


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

    lipsync_requested = bool(data.get("lipsync"))

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
    alignment = align_text(text)
    alignment_path: Optional[Path] = None
    lipsync_path: Optional[Path] = None

    artifact_value = result.get("path")
    if artifact_value:
        artifact_path = Path(artifact_value)
        root = artifact_path.parent
        alignment_path = root / "alignment.json"
        write_alignment(alignment, alignment_path)

        sidecar_value = result.get("sidecar")
        sidecar_path = Path(sidecar_value) if sidecar_value else None
        sidecar_payload = _read_json(sidecar_path) if sidecar_path else {}
        sidecar_payload["alignment"] = alignment
        sidecar_payload["alignment_path"] = str(alignment_path)

        if lipsync_requested:
            lipsync_payload = alignment_to_lipsync_payload(alignment)
            lipsync_path = root / "lipsync.json"
            _write_json(lipsync_path, lipsync_payload)
            sidecar_payload["lipsync"] = {
                "path": str(lipsync_path),
                "fps": lipsync_payload["fps"],
                "frame_count": len(lipsync_payload["frames"]),
            }

        if sidecar_path:
            _write_json(sidecar_path, sidecar_payload)
            result["sidecar"] = str(sidecar_path)

    response = dict(result)
    response["alignment"] = alignment
    if alignment_path:
        response["alignment_path"] = str(alignment_path)
    if lipsync_path:
        response["lipsync_path"] = str(lipsync_path)

    return {"ok": True, "data": response}


@router.post("/music/remix")
async def music_remix(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _expect_dict(payload)

    track_path = str(data.get("track") or "")
    style = str(data.get("style") or "ambient")

    LOGGER.info("Music remix request track=%s style=%s", track_path, style)
    result = remix(track_path, style)
    return {"ok": True, "data": result}


def _build_track_spec(entry: Dict[str, Any]) -> TrackSpec:
    path_value = entry.get("path")
    if not path_value:
        raise HTTPException(status_code=400, detail="track path required")
    path = Path(str(path_value))
    role = str(entry.get("role") or "bgm")
    name = entry.get("name")

    def _float_field(key: str, default: float = 0.0) -> float:
        value = entry.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail=f"{key} must be numeric"
            ) from None

    gain = _float_field("gain", 1.0)
    gain_db = _float_field("gain_db", 0.0)
    offset = _float_field("offset", 0.0)

    return TrackSpec(
        path=path,
        role=role,
        name=str(name) if name is not None else None,
        gain=gain,
        gain_db=gain_db,
        offset=offset,
    )


def _build_ducking(entry: Dict[str, Any]) -> DuckingConfig:
    trigger_roles = _sanitize_roles(
        entry.get("trigger_roles"),
        default=("voice",),
    )
    target_roles = _sanitize_roles(
        entry.get("target_roles"),
        default=("bgm",),
    )

    def _float_value(key: str, default: float) -> float:
        value = entry.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail=f"ducking.{key} must be numeric"
            ) from None

    return DuckingConfig(
        trigger_roles=tuple(trigger_roles),
        target_roles=tuple(target_roles),
        amount_db=_float_value("amount_db", 9.0),
        threshold=_float_value("threshold", 0.02),
        attack_ms=_float_value("attack_ms", 45.0),
        release_ms=_float_value("release_ms", 160.0),
    )


def _mix_cache_key(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


@router.post("/audio/mix")
async def audio_mix(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _expect_dict(payload)

    tracks_input = data.get("tracks")
    if not isinstance(tracks_input, list) or not tracks_input:
        raise HTTPException(status_code=400, detail="tracks must be a non-empty list")

    track_specs = [_build_track_spec(entry) for entry in tracks_input]

    duck_cfg: Optional[DuckingConfig] = None
    duck_payload: Optional[Dict[str, Any]] = None
    raw_ducking = data.get("ducking")
    if isinstance(raw_ducking, dict):
        duck_cfg = _build_ducking(raw_ducking)
        duck_payload = {
            "trigger_roles": list(duck_cfg.trigger_roles),
            "target_roles": list(duck_cfg.target_roles),
            "amount_db": duck_cfg.amount_db,
            "threshold": duck_cfg.threshold,
            "attack_ms": duck_cfg.attack_ms,
            "release_ms": duck_cfg.release_ms,
        }

    sample_rate = data.get("sample_rate")
    if sample_rate is not None:
        try:
            sample_rate = int(sample_rate)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="sample_rate must be integer"
            ) from None
        if sample_rate <= 0:
            raise HTTPException(status_code=400, detail="sample_rate must be positive")

    cache_payload = {
        "tracks": [
            {
                "path": str(spec.path.resolve()),
                "role": spec.role,
                "name": spec.name,
                "gain": spec.gain,
                "gain_db": spec.gain_db,
                "offset": spec.offset,
            }
            for spec in track_specs
        ],
        "ducking": duck_payload,
        "sample_rate": sample_rate,
    }
    cache_key = _mix_cache_key(cache_payload)

    mix_root = _MIX_ROOT / cache_key
    output_path = mix_root / "mix.wav"
    sidecar_path = mix_root / "mix.json"
    cached = output_path.exists() and sidecar_path.exists()

    metadata: Dict[str, Any]
    if cached:
        metadata = _read_json(sidecar_path)
        if not metadata:
            cached = False

    if not cached:
        mix_root.mkdir(parents=True, exist_ok=True)
        try:
            metadata = mix_tracks(
                track_specs,
                output_path=output_path,
                sidecar_path=sidecar_path,
                ducking=duck_cfg,
                sample_rate=sample_rate,
            )
        except FileNotFoundError as exc:
            LOGGER.warning("Audio mix missing track: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Audio mix failed")
            raise HTTPException(status_code=500, detail="mix failed") from exc
    else:
        metadata.setdefault("sidecar", str(sidecar_path))

    metadata["cache_key"] = cache_key
    _write_json(sidecar_path, metadata)

    response: Dict[str, Any] = {
        "cache_key": cache_key,
        "path": str(output_path),
        "sidecar": metadata.get("sidecar", str(sidecar_path)),
        "duration": metadata.get("duration"),
        "sample_rate": metadata.get("sample_rate"),
        "tracks": metadata.get("tracks"),
        "ducking": metadata.get("ducking"),
        "cached": cached,
    }
    return {"ok": True, "data": response}
