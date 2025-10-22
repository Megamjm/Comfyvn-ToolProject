from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.anim.rig import autorig, mograph
from comfyvn.config import feature_flags

try:  # optional for CLI utilities
    from comfyvn.core import modder_hooks  # type: ignore
    from comfyvn.core.modder_hooks import HookSpec  # type: ignore
except Exception:  # pragma: no cover - optional import guard
    modder_hooks = None  # type: ignore
    HookSpec = None  # type: ignore

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anim", tags=["Animation 2.5D"])

FEATURE_FLAG = "enable_anim_25d"
PRESET_PATH = Path("cache/anim_25d_presets.json")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_enabled() -> None:
    if feature_flags.is_enabled(FEATURE_FLAG, default=False):
        return
    raise HTTPException(status_code=403, detail=f"{FEATURE_FLAG} disabled")


def _register_hook_specs() -> None:
    if modder_hooks is None or HookSpec is None:  # pragma: no cover - optional hook bus
        return
    spec_map = modder_hooks.HOOK_SPECS
    if "on_anim_rig_generated" not in spec_map:
        spec_map["on_anim_rig_generated"] = HookSpec(
            name="on_anim_rig_generated",
            description="Emitted after the auto-rig builder produces a deterministic 2.5D rig.",
            payload_fields={
                "character": "Character identifier supplied in the rig request.",
                "checksum": "Deterministic checksum representing the rig output.",
                "stats": "Summary statistics returned by the rig builder (bone counts, roles).",
                "anchors": "Number of anchors that were converted into bones.",
                "timestamp": "UTC timestamp when the rig was produced.",
            },
            ws_topic="modder.on_anim_rig_generated",
            rest_event="on_anim_rig_generated",
        )
    if "on_anim_preview_generated" not in spec_map:
        spec_map["on_anim_preview_generated"] = HookSpec(
            name="on_anim_preview_generated",
            description="Emitted after the preview endpoint composes an idle/turn/emote loop.",
            payload_fields={
                "character": "Character identifier tied to the preview request.",
                "checksum": "Rig checksum used to drive the preview.",
                "frames": "Number of frames included in the preview loop.",
                "duration": "Length of the preview loop in seconds.",
                "states": "Ordered list of motion graph states for the preview loop.",
                "timestamp": "UTC timestamp when the preview was generated.",
            },
            ws_topic="modder.on_anim_preview_generated",
            rest_event="on_anim_preview_generated",
        )
    if "on_anim_preset_saved" not in spec_map:
        spec_map["on_anim_preset_saved"] = HookSpec(
            name="on_anim_preset_saved",
            description="Emitted after a 2.5D rig preset is written to the local preset catalog.",
            payload_fields={
                "name": "Preset name that was persisted.",
                "checksum": "Deterministic rig checksum associated with the preset.",
                "character": "Optional character identifier tagged to the preset.",
                "path": "Absolute filesystem path to the preset catalog JSON.",
                "timestamp": "UTC timestamp when the preset was stored.",
            },
            ws_topic="modder.on_anim_preset_saved",
            rest_event="on_anim_preset_saved",
        )


_register_hook_specs()


def _emit_hook(event: str, payload: Mapping[str, Any]) -> None:
    if modder_hooks is None:
        return
    try:
        modder_hooks.emit(event, dict(payload))
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.debug(
            "Animation hook '%s' emission failed: %s", event, exc, exc_info=True
        )


def _load_presets() -> MutableMapping[str, Any]:
    if not PRESET_PATH.exists():
        return {}
    try:
        data = json.loads(PRESET_PATH.read_text(encoding="utf-8") or "{}")
        if isinstance(data, dict):
            return dict(data)
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Failed to load presets from %s: %s", PRESET_PATH, exc)
    return {}


def _save_presets(payload: Mapping[str, Any]) -> None:
    PRESET_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESET_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


class RigRequest(BaseModel):
    character: str | None = Field(
        default=None, description="Identifier or label for the character rig."
    )
    anchors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Anchor payload describing layer pivots to convert into bones.",
    )
    options: dict[str, Any] | None = Field(
        default=None,
        description="Optional tuning parameters forwarded to the rig builder.",
    )

    model_config = ConfigDict(extra="allow")


class PreviewRequest(RigRequest):
    fps: int | None = Field(
        default=None, description="Override frames per second for the preview loop."
    )
    duration: float | None = Field(
        default=None,
        description="Rough target duration for the generated preview loop (seconds).",
    )
    sequence: list[str] | None = Field(
        default=None,
        description="Optional viseme sequence for the emote pass (e.g. ['A','I','U']).",
    )

    model_config = ConfigDict(extra="allow")


class SavePresetRequest(RigRequest):
    name: str = Field(..., description="Human-readable preset name.")
    description: str | None = Field(
        default=None, description="Optional preset description."
    )
    overwrite: bool = Field(
        default=False,
        description="When true, allow overwriting an existing preset with the same name.",
    )
    rig: dict[str, Any] | None = Field(
        default=None,
        description="Optional rig payload to persist (skips re-running auto-rig).",
    )
    preview: dict[str, Any] | None = Field(
        default=None,
        description="Optional preview payload to store alongside the preset.",
    )

    model_config = ConfigDict(extra="allow")


def _build_rig_from_request(request: RigRequest) -> Dict[str, Any]:
    if not request.anchors and not request.options:
        raise HTTPException(
            status_code=400,
            detail="Rig requests must contain at least one anchor entry.",
        )
    try:
        return autorig.build_rig(
            request.anchors,
            character=request.character,
            options=request.options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rig")
async def generate_rig(payload: RigRequest) -> Mapping[str, Any]:
    _require_enabled()
    rig_payload = _build_rig_from_request(payload)
    idle_cycle = autorig.generate_idle_cycle(rig_payload)
    rig_payload["idle_cycle"] = idle_cycle
    response = {
        "rig": rig_payload,
        "idle": idle_cycle,
        "timestamp": _utc_timestamp(),
    }
    _emit_hook(
        "on_anim_rig_generated",
        {
            "character": rig_payload.get("character"),
            "checksum": rig_payload.get("checksum"),
            "stats": rig_payload.get("stats"),
            "anchors": len(payload.anchors),
            "timestamp": response["timestamp"],
        },
    )
    LOGGER.info(
        "Generated 2.5D rig character=%s checksum=%s bones=%s",
        rig_payload.get("character"),
        rig_payload.get("checksum"),
        rig_payload.get("stats", {}).get("bone_count"),
    )
    return response


@router.post("/preview")
async def preview_animation(payload: PreviewRequest) -> Mapping[str, Any]:
    _require_enabled()
    rig_payload = _build_rig_from_request(payload)
    idle_cycle = autorig.generate_idle_cycle(
        rig_payload,
        duration=float(payload.duration or autorig.DEFAULT_IDLE_DURATION),
        fps=int(payload.fps or autorig.DEFAULT_IDLE_FPS),
    )
    graph = mograph.MotionGraph(rig_payload, idle_cycle=idle_cycle)
    preview_loop = graph.generate_preview_loop(
        duration=float(payload.duration or 4.0),
        fps=int(payload.fps or mograph.DEFAULT_FPS),
    )
    if payload.sequence:
        preview_loop["sequence"] = payload.sequence

    response = {
        "rig": rig_payload,
        "idle": idle_cycle,
        "preview": preview_loop,
        "timestamp": _utc_timestamp(),
    }
    _emit_hook(
        "on_anim_preview_generated",
        {
            "character": rig_payload.get("character"),
            "checksum": rig_payload.get("checksum"),
            "frames": len(preview_loop.get("frames", [])),
            "duration": preview_loop.get("duration"),
            "states": preview_loop.get("states"),
            "timestamp": response["timestamp"],
        },
    )
    LOGGER.debug(
        "Preview loop generated character=%s frames=%s duration=%s",
        rig_payload.get("character"),
        len(preview_loop.get("frames", [])),
        preview_loop.get("duration"),
    )
    return response


def _sanitize_preset_name(name: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.strip())
    slug = slug.strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.lower() or "anim-preset"


@router.post("/save")
async def save_preset(payload: SavePresetRequest) -> Mapping[str, Any]:
    _require_enabled()
    safe_name = _sanitize_preset_name(payload.name)
    presets = _load_presets()
    existing = presets.get(safe_name)
    if existing and not payload.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"Preset '{safe_name}' already exists. Pass overwrite=true to replace it.",
        )

    rig_payload: Dict[str, Any]
    if payload.rig:
        rig_payload = dict(payload.rig)
    else:
        rig_payload = _build_rig_from_request(payload)
    idle_cycle = rig_payload.get("idle_cycle") or autorig.generate_idle_cycle(
        rig_payload
    )
    preview_payload = payload.preview
    if not preview_payload:
        graph = mograph.MotionGraph(rig_payload, idle_cycle=idle_cycle)
        preview_payload = graph.generate_preview_loop()

    preset_entry = {
        "name": safe_name,
        "display_name": payload.name,
        "character": rig_payload.get("character"),
        "checksum": rig_payload.get("checksum"),
        "rig": rig_payload,
        "idle": idle_cycle,
        "preview": preview_payload,
        "description": payload.description,
        "saved_at": _utc_timestamp(),
    }
    presets[safe_name] = preset_entry
    _save_presets(presets)
    _emit_hook(
        "on_anim_preset_saved",
        {
            "name": payload.name,
            "checksum": rig_payload.get("checksum"),
            "character": rig_payload.get("character"),
            "path": str(PRESET_PATH.resolve()),
            "timestamp": preset_entry["saved_at"],
        },
    )
    LOGGER.info(
        "Animation preset saved name=%s checksum=%s path=%s",
        safe_name,
        rig_payload.get("checksum"),
        PRESET_PATH,
    )
    return {
        "preset": preset_entry,
        "path": str(PRESET_PATH),
        "timestamp": preset_entry["saved_at"],
    }


__all__ = ["router"]
