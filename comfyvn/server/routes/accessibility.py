from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.accessibility import accessibility_manager
from comfyvn.accessibility import filters as accessibility_filters
from comfyvn.accessibility.input_map import InputBinding, input_map_manager
from comfyvn.config import feature_flags

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accessibility", tags=["Accessibility"])
input_router = APIRouter(prefix="/api/input", tags=["Input"])


class AccessibilitySettingsPayload(BaseModel):
    font_scale: float = Field(default=1.0, ge=0.5, le=3.0)
    color_filter: str = Field(default="none")
    high_contrast: bool = Field(default=False)
    subtitles_enabled: bool = Field(default=True)
    ui_scale: float = Field(default=1.0, ge=1.0, le=2.0)
    view_overrides: dict[str, float] = Field(default_factory=dict)


class AccessibilityStateResponse(AccessibilitySettingsPayload):
    subtitle_text: str = ""
    subtitle_origin: str | None = None
    subtitle_expires_at: float | None = None


class SubtitlePayload(BaseModel):
    text: str = ""
    origin: str | None = None
    ttl: float | None = Field(default=5.0, ge=0.0, le=120.0)


class InputBindingModel(BaseModel):
    action: str
    label: str
    primary: str | None = None
    secondary: str | None = None
    gamepad: str | None = None
    category: str = "viewer"


class UpdateInputBindingPayload(BaseModel):
    action: str
    primary: str | None = Field(default=None)
    secondary: str | None = Field(default=None)
    gamepad: str | None = Field(default=None)


class TriggerInputPayload(BaseModel):
    action: str
    meta: dict[str, Any] | None = None


class AccessibilityProfilePayload(BaseModel):
    accessibility: AccessibilitySettingsPayload | None = None
    input_bindings: dict[str, Any] | None = None
    merge_bindings: bool = Field(default=False)


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("enable_accessibility", default=False):
        raise HTTPException(
            status_code=403, detail="Accessibility disabled by feature flag."
        )
    if feature_flags.is_enabled("enable_accessibility_api", default=True):
        return
    raise HTTPException(
        status_code=403, detail="Accessibility API disabled by feature flag."
    )


def _state_payload() -> dict:
    snapshot = accessibility_manager.snapshot()
    data = asdict(snapshot)
    data["color_filter"] = accessibility_filters.canonical_filter_key(
        data.get("color_filter", "none")
    )
    overrides = data.get("view_overrides") or {}
    data["view_overrides"] = {str(k): float(v) for k, v in overrides.items()}
    return data


def _serialize_input_map() -> dict[str, Any]:
    bindings = [
        InputBindingModel.model_validate(binding.to_dict())
        for binding in input_map_manager.bindings().values()
    ]
    options = [
        {"key": key, "label": label}
        for key, label in input_map_manager.available_gamepad_bindings()
    ]
    return {
        "bindings": [binding.model_dump() for binding in bindings],
        "gamepad_options": options,
        "controller_enabled": feature_flags.is_enabled(
            "enable_controller_profiles", default=True
        ),
    }


async def _update_input_binding(
    payload: UpdateInputBindingPayload,
) -> InputBindingModel:
    binding = input_map_manager.update_binding(
        payload.action,
        primary=payload.primary,
        secondary=payload.secondary,
        gamepad=payload.gamepad,
    )
    LOGGER.info(
        "Input binding updated via API",
        extra={
            "event": "api.accessibility.input_map.post",
            "binding": binding.to_dict(),
        },
    )
    return InputBindingModel.model_validate(binding.to_dict())


@router.get("/state", response_model=AccessibilityStateResponse)
async def accessibility_state_snapshot() -> AccessibilityStateResponse:
    _ensure_enabled()
    return AccessibilityStateResponse.model_validate(_state_payload())


@router.post("/state", response_model=AccessibilityStateResponse)
async def update_accessibility_state(
    payload: AccessibilitySettingsPayload,
) -> AccessibilityStateResponse:
    _ensure_enabled()
    accessibility_manager.update(**payload.model_dump())
    LOGGER.info(
        "Accessibility state updated via API",
        extra={
            "event": "api.accessibility.state.post",
            "accessibility": payload.model_dump(),
        },
    )
    return AccessibilityStateResponse.model_validate(_state_payload())


@router.post("/set", response_model=AccessibilityStateResponse)
async def set_accessibility_state(
    payload: AccessibilitySettingsPayload,
) -> AccessibilityStateResponse:
    return await update_accessibility_state(payload)


@router.get("/export")
async def export_accessibility_profile() -> dict[str, Any]:
    _ensure_enabled()
    return {
        "accessibility": accessibility_manager.export_profile(),
        "input_bindings": input_map_manager.export_bindings(),
    }


@router.post("/import", response_model=AccessibilityStateResponse)
async def import_accessibility_profile(
    payload: AccessibilityProfilePayload,
) -> AccessibilityStateResponse:
    _ensure_enabled()
    merged_state: AccessibilityStateResponse | None = None
    if payload.accessibility is not None:
        accessibility_manager.update(**payload.accessibility.model_dump())
        merged_state = AccessibilityStateResponse.model_validate(_state_payload())
    if payload.input_bindings:
        input_map_manager.import_bindings(
            payload.input_bindings, merge=payload.merge_bindings
        )
    LOGGER.info(
        "Accessibility profile imported via API",
        extra={
            "event": "api.accessibility.import",
            "merge": payload.merge_bindings,
            "accessibility": bool(payload.accessibility),
            "bindings": len(payload.input_bindings or {}),
        },
    )
    return (
        merged_state
        if merged_state is not None
        else AccessibilityStateResponse.model_validate(_state_payload())
    )


@router.get("/filters")
async def list_accessibility_filters() -> dict[str, list[dict[str, str]]]:
    _ensure_enabled()
    return {"filters": accessibility_filters.list_filters()}


@router.post("/subtitle", response_model=AccessibilityStateResponse)
async def push_accessibility_subtitle(
    payload: SubtitlePayload = Body(...),
) -> AccessibilityStateResponse:
    _ensure_enabled()
    text = payload.text.strip()
    if text:
        accessibility_manager.push_subtitle(
            text,
            origin=payload.origin,
            ttl=payload.ttl or 0.0,
        )
        LOGGER.info(
            "Accessibility subtitle pushed via API",
            extra={
                "event": "api.accessibility.subtitle.post",
                "subtitle": {
                    "text": text,
                    "origin": payload.origin,
                    "ttl": payload.ttl,
                },
            },
        )
    else:
        accessibility_manager.clear_subtitle()
        LOGGER.info(
            "Accessibility subtitle cleared via API",
            extra={"event": "api.accessibility.subtitle.clear"},
        )
    return AccessibilityStateResponse.model_validate(_state_payload())


@router.delete("/subtitle", response_model=AccessibilityStateResponse)
async def clear_accessibility_subtitle() -> AccessibilityStateResponse:
    _ensure_enabled()
    accessibility_manager.clear_subtitle()
    LOGGER.info(
        "Accessibility subtitle cleared via API",
        extra={"event": "api.accessibility.subtitle.delete"},
    )
    return AccessibilityStateResponse.model_validate(_state_payload())


@router.get("/input-map")
async def get_input_map() -> dict[str, Any]:
    _ensure_enabled()
    return _serialize_input_map()


@router.post("/input-map", response_model=InputBindingModel)
async def update_input_map(payload: UpdateInputBindingPayload) -> InputBindingModel:
    _ensure_enabled()
    return await _update_input_binding(payload)


@router.post("/input/event")
async def trigger_input_event(payload: TriggerInputPayload) -> dict[str, Any]:
    _ensure_enabled()
    ok = input_map_manager.trigger(
        payload.action,
        source="api",
        meta=payload.meta or {},
    )
    LOGGER.info(
        "Input action triggered via API",
        extra={
            "event": "api.accessibility.input.trigger",
            "action": payload.action,
            "meta": payload.meta or {},
        },
    )
    return {"ok": ok}


@input_router.get("/map")
async def input_router_get_map() -> dict[str, Any]:
    return await get_input_map()


@input_router.post("/map", response_model=InputBindingModel)
async def input_router_update_map(
    payload: UpdateInputBindingPayload,
) -> InputBindingModel:
    _ensure_enabled()
    return await _update_input_binding(payload)


@input_router.post("/reset")
async def input_router_reset_map() -> dict[str, Any]:
    _ensure_enabled()
    input_map_manager.reset()
    state = _serialize_input_map()
    state["ok"] = True
    LOGGER.info(
        "Input bindings reset via API",
        extra={"event": "api.input.reset"},
    )
    return state


__all__ = [
    "router",
    "input_router",
    "AccessibilitySettingsPayload",
    "AccessibilityStateResponse",
    "SubtitlePayload",
    "AccessibilityProfilePayload",
    "InputBindingModel",
    "UpdateInputBindingPayload",
    "TriggerInputPayload",
]
