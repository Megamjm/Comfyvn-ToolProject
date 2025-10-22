from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Mapping, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.core.modder_hooks import HookSpec
from comfyvn.props import (
    ALPHA_MODES,
    DEFAULT_TWEEN,
    PROP_MANAGER,
    TWEEN_KINDS,
    Z_ORDER_VALUES,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/props", tags=["Props"])


class EnsurePropRequest(BaseModel):
    prop_id: str = Field(alias="id")
    asset: str
    style: str | None = None
    tags: list[str] | None = None
    checksum: str | None = None
    metadata: dict[str, Any] | None = None
    generator: str | None = None
    alpha_mode: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ApplyPropRequest(BaseModel):
    prop_id: str
    anchor: str = "center"
    z_order: str | None = Field(default="over_portrait")
    conditions: list[str] | str | None = None
    tween: Mapping[str, Any] | None = None
    state: Mapping[str, Any] | None = None

    model_config = ConfigDict(extra="ignore")


class RemovePropRequest(BaseModel):
    prop_id: str = Field(alias="id")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


def _ensure_enabled() -> None:
    if feature_flags.is_enabled("enable_props", default=False):
        return
    raise HTTPException(status_code=403, detail="enable_props disabled")


def _install_hook_specs() -> None:
    applied_spec = HookSpec(
        name="on_prop_applied",
        description="Emitted when a visual prop evaluation attaches to a scene anchor.",
        payload_fields={
            "prop_id": "Prop identifier passed into ensure_prop/apply.",
            "anchor": "Anchor payload containing id/x/y/group metadata.",
            "z_order": "Layer bucket for the prop (under_bg/under_portrait/over_portrait/over_ui).",
            "visible": "Boolean result after evaluating the supplied conditions.",
            "tween": "Tween payload with kind/duration/ease/hold/loop/stop_at_end/caps.",
            "evaluations": "Dictionary of condition expressions mapped to boolean evaluations.",
            "thumbnail": "Thumbnail path returned by ensure_prop when available.",
            "sidecar": "Sidecar payload describing provenance, generator, alpha mode.",
            "context": "Whitelisted evaluation context (weather/pose/emotion).",
            "applied_at": "UTC timestamp when the evaluation occurred.",
        },
        ws_topic="modder.on_prop_applied",
        rest_event="on_prop_applied",
    )
    removal_spec = HookSpec(
        name="on_prop_removed",
        description="Emitted when an ensured prop entry is removed from the registry.",
        payload_fields={
            "prop_id": "Prop identifier removed from the registry.",
            "thumbnail": "Thumbnail path that was linked to the prop.",
            "sidecar": "Sidecar payload returned from ensure_prop.",
            "provenance": "Original ensure provenance payload.",
            "removed_at": "UTC timestamp for the removal action.",
        },
        ws_topic="modder.on_prop_removed",
        rest_event="on_prop_removed",
    )
    modder_hooks.HOOK_SPECS["on_prop_applied"] = applied_spec
    if "on_prop_removed" not in modder_hooks.HOOK_SPECS:
        modder_hooks.HOOK_SPECS["on_prop_removed"] = removal_spec
    bus = getattr(modder_hooks, "_BUS", None)
    if bus is not None:
        with bus._lock:  # type: ignore[attr-defined]
            bus._listeners.setdefault("on_prop_applied", [])  # type: ignore[attr-defined]
            bus._listeners.setdefault("on_prop_removed", [])  # type: ignore[attr-defined]


_install_hook_specs()


@router.get("/anchors")
async def list_prop_anchors() -> Mapping[str, Any]:
    tween_defaults = deepcopy(DEFAULT_TWEEN)
    return {
        "anchors": PROP_MANAGER.anchors,
        "z_order": list(Z_ORDER_VALUES),
        "tween": {
            "defaults": tween_defaults,
            "kinds": list(TWEEN_KINDS),
        },
        "alpha_modes": list(ALPHA_MODES),
    }


@router.post("/ensure")
async def ensure_prop(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _ensure_enabled()
    try:
        request = EnsurePropRequest.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = PROP_MANAGER.ensure_prop(
            prop_id=request.prop_id,
            asset=request.asset,
            style=request.style,
            tags=request.tags,
            checksum=request.checksum,
            metadata=request.metadata,
            generator=request.generator,
            alpha_mode=request.alpha_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.info(
        "Prop ensured",
        extra={
            "prop_id": result["prop"]["id"],
            "deduped": result["deduped"],
            "thumbnail": result["thumbnail"],
        },
    )
    return result


@router.post("/apply")
async def apply_prop(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _ensure_enabled()
    try:
        request = ApplyPropRequest.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conditions: Optional[list[str] | str]
    if isinstance(request.conditions, list):
        conditions = request.conditions
    else:
        conditions = request.conditions

    state_payload = request.state if isinstance(request.state, Mapping) else None

    try:
        result = PROP_MANAGER.apply_prop(
            prop_id=request.prop_id,
            anchor=request.anchor,
            z_order=request.z_order,
            conditions=conditions,
            tween=request.tween,
            state=state_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    LOGGER.debug(
        "Prop applied id=%s anchor=%s visible=%s z_order=%s",
        result["prop_id"],
        result["anchor"]["id"],
        result["visible"],
        result["z_order"],
    )

    hook_payload = {
        "prop_id": result["prop_id"],
        "anchor": result["anchor"],
        "z_order": result["z_order"],
        "visible": result["visible"],
        "tween": result["tween"],
        "evaluations": result["evaluations"],
        "thumbnail": result.get("thumbnail"),
        "sidecar": result.get("sidecar"),
        "context": result.get("context", {}),
        "applied_at": result["applied_at"],
    }
    try:
        modder_hooks.emit("on_prop_applied", hook_payload)
    except Exception:
        LOGGER.warning("modder hook on_prop_applied failed", exc_info=True)

    return result


@router.post("/remove")
async def remove_prop(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _ensure_enabled()
    try:
        request = RemovePropRequest.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    removed = PROP_MANAGER.remove_prop(prop_id=request.prop_id)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"prop '{request.prop_id}' not found"
        )

    hook_payload = {
        "prop_id": removed["prop"]["id"],
        "thumbnail": removed.get("thumbnail"),
        "sidecar": removed.get("sidecar"),
        "provenance": removed.get("provenance"),
        "removed_at": removed["removed_at"],
    }
    try:
        modder_hooks.emit("on_prop_removed", hook_payload)
    except Exception:
        LOGGER.warning("modder hook on_prop_removed failed", exc_info=True)
    LOGGER.info("Prop removed", extra={"prop_id": removed["prop"]["id"]})
    return removed


@router.get("")
async def list_props() -> Mapping[str, Any]:
    _ensure_enabled()
    return {"props": PROP_MANAGER.list_props()}


__all__ = ["router", "EnsurePropRequest", "ApplyPropRequest", "RemovePropRequest"]
