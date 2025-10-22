from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.pov import WORLDLINES
from comfyvn.pov.worldlines import LANE_OFFICIAL, LANE_VN_BRANCH
from comfyvn.themes import available_templates
from comfyvn.themes import plan as plan_theme

try:  # Optional for CLI utilities
    from comfyvn.core import modder_hooks  # type: ignore
except Exception:  # pragma: no cover - optional import guard
    modder_hooks = None  # type: ignore

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/themes", tags=["Themes"])

FEATURE_FLAG = "enable_themes"


def _require_enabled() -> None:
    if not feature_flags.is_enabled(FEATURE_FLAG):
        raise HTTPException(status_code=403, detail=f"{FEATURE_FLAG} disabled")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _register_theme_hooks() -> None:
    if modder_hooks is None:
        return
    spec_map = modder_hooks.HOOK_SPECS
    if "on_theme_preview" not in spec_map:
        spec_map["on_theme_preview"] = modder_hooks.HookSpec(
            name="on_theme_preview",
            description="Emitted after a theme kit preview delta is constructed.",
            payload_fields={
                "theme": "Canonical theme identifier.",
                "theme_label": "Human readable label for the theme kit.",
                "subtype": "Resolved subtype key applied to the kit.",
                "variant": "Accessibility variant applied (base|high_contrast|color_blind).",
                "anchors_preserved": "List of anchor identifiers flagged for preservation.",
                "plan": "Plan delta payload returned by comfyvn.themes.plan.",
                "scene": "Scene snapshot supplied by the caller.",
                "timestamp": "UTC ISO8601 timestamp when the preview was generated.",
            },
            ws_topic="modder.on_theme_preview",
            rest_event="on_theme_preview",
        )
    if "on_theme_apply" not in spec_map:
        spec_map["on_theme_apply"] = modder_hooks.HookSpec(
            name="on_theme_apply",
            description="Emitted after a theme kit is committed to a VN Branch worldline.",
            payload_fields={
                "theme": "Canonical theme identifier.",
                "theme_label": "Human readable label for the theme kit.",
                "subtype": "Resolved subtype key applied to the kit.",
                "variant": "Accessibility variant applied (base|high_contrast|color_blind).",
                "anchors_preserved": "List of anchor identifiers flagged for preservation.",
                "plan": "Plan delta payload returned by comfyvn.themes.plan.",
                "branch": "Worldline snapshot for the created/updated VN Branch lane.",
                "branch_created": "Boolean flag indicating whether the branch was newly created.",
                "checksum": "Stable checksum returned by the plan payload.",
                "scene": "Scene snapshot supplied by the caller.",
                "timestamp": "UTC ISO8601 timestamp when the apply call completed.",
            },
            ws_topic="modder.on_theme_apply",
            rest_event="on_theme_apply",
        )


_register_theme_hooks()


def _emit_hook(event: str, payload: Dict[str, Any]) -> None:
    if modder_hooks is None:
        return
    try:
        modder_hooks.emit(event, payload)
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.debug("Theme hook '%s' emission failed: %s", event, exc, exc_info=True)


def _slugify(value: str, *, default: str = "theme") -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    text = text.strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or default


class ThemeRequestPayload(BaseModel):
    theme: str = Field(
        ..., description="Theme kit identifier (ModernSchool, UrbanNoir, Gothic, etc.)."
    )
    subtype: str | None = Field(
        default=None, description="Optional kit subtype label or id to apply."
    )
    variant: str | None = Field(
        default=None,
        description="Accessibility variant (base|high_contrast|color_blind).",
    )
    anchors: List[str] | None = Field(
        default=None,
        description="Anchor identifiers to preserve when composing the swap plan.",
    )
    scene: Dict[str, Any] = Field(
        default_factory=dict, description="Optional scene or world state snapshot."
    )
    overrides: Dict[str, Any] | None = Field(
        default=None,
        description="Optional overrides, e.g. {'characters': {'alice': {...}}}.",
    )

    model_config = ConfigDict(extra="allow")


class ThemePreviewPayload(ThemeRequestPayload):
    pass


class ThemeApplyPayload(ThemeRequestPayload):
    branch_label: str | None = Field(
        default=None,
        description="Optional label override for the VN Branch worldline created by the swap.",
    )


class ThemePreviewResponse(BaseModel):
    plan_delta: Dict[str, Any]
    templates: List[Dict[str, Any]]

    model_config = ConfigDict(extra="allow")


class ThemeApplyResponse(ThemePreviewResponse):
    branch: Dict[str, Any] | None = None
    branch_created: bool = False

    model_config = ConfigDict(extra="allow")


def _build_plan_payload(payload: ThemeRequestPayload) -> Dict[str, Any]:
    return plan_theme(
        payload.theme,
        payload.scene,
        subtype=payload.subtype,
        anchors=payload.anchors,
        overrides=payload.overrides,
        variant=payload.variant,
    )


def _ensure_source_world(world_id: str, scene: Mapping[str, Any]):
    try:
        return WORLDLINES.ensure(world_id)
    except KeyError:
        label = (
            scene.get("world_label")
            or scene.get("label")
            or world_id.replace("_", " ").title()
        )
        pov = (
            scene.get("pov")
            or scene.get("pov_id")
            or scene.get("povSlug")
            or "narrator"
        )
        root_node = scene.get("root_node") or scene.get("scene_id") or "start"
        world, _created, _snapshot = WORLDLINES.create_or_update(
            world_id,
            label=str(label),
            pov=str(pov),
            root_node=str(root_node),
            metadata={"provenance": []},
            lane=LANE_OFFICIAL,
            set_active=False,
        )
        return world


def _merge_metadata(
    existing: Mapping[str, Any], overlay: Mapping[str, Any]
) -> Dict[str, Any]:
    result: Dict[str, Any] = dict(existing or {})
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge_metadata(result[key], value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            merged_list = list(result.get(key) or [])
            for entry in value:
                if entry not in merged_list:
                    merged_list.append(entry)
            result[key] = merged_list
        else:
            result[key] = value
    return result


def _build_branch_metadata(
    plan_delta: Mapping[str, Any], *, timestamp: str
) -> Dict[str, Any]:
    metadata = plan_delta.get("metadata", {})
    preserved = metadata.get("anchors_preserved") or []
    changed_keys = [
        key
        for key, value in (plan_delta.get("mutations") or {}).items()
        if isinstance(value, Mapping) and value.get("changed")
    ]
    provenance_entry = {
        "event": "theme_swap",
        "theme": plan_delta.get("theme"),
        "theme_label": metadata.get("template_label"),
        "subtype": metadata.get("subtype"),
        "variant": metadata.get("variant"),
        "anchors": preserved,
        "checksum": plan_delta.get("checksum"),
        "timestamp": timestamp,
    }
    return {
        "theme_swap": {
            "theme": plan_delta.get("theme"),
            "theme_label": metadata.get("template_label"),
            "subtype": metadata.get("subtype"),
            "subtype_label": metadata.get("subtype_label"),
            "variant": metadata.get("variant"),
            "variant_label": metadata.get("variant_label"),
            "anchors_preserved": preserved,
            "mutations_changed": changed_keys,
            "preview": plan_delta.get("preview"),
            "checksum": plan_delta.get("checksum"),
            "updated_at": timestamp,
        },
        "provenance": [provenance_entry],
    }


def _create_theme_branch(
    plan_delta: Mapping[str, Any],
    payload: ThemeApplyPayload,
) -> tuple[Dict[str, Any], bool]:
    scene_state = payload.scene or {}
    world_id = str(
        plan_delta.get("world_id")
        or scene_state.get("world_id")
        or scene_state.get("world")
        or "world"
    )
    source_world = _ensure_source_world(world_id, scene_state)
    metadata = plan_delta.get("metadata", {})
    subtype_key = metadata.get("subtype") or "default"
    variant_key = metadata.get("variant") or "base"

    slug_parts = [
        _slugify(plan_delta.get("theme_label") or plan_delta.get("theme")),
        _slugify(subtype_key),
    ]
    if variant_key and variant_key not in {"base"}:
        slug_parts.append(_slugify(variant_key))
    branch_id = f"{source_world.id}--{'-'.join(slug_parts)}"

    subtype_label = metadata.get("subtype_label") or subtype_key.title()
    branch_label = payload.branch_label or (
        f"{plan_delta.get('theme_label', plan_delta.get('theme'))} - {subtype_label}"
    )

    timestamp = _utc_timestamp()
    metadata_overlay = _build_branch_metadata(plan_delta, timestamp=timestamp)

    # Attempt to create the branch by forking OFFICIAL lane.
    try:
        branch_world = WORLDLINES.ensure(branch_id)
        created = False
    except KeyError:
        branch_world, created, _snapshot = WORLDLINES.fork(
            source_world.id,
            branch_id,
            label=branch_label,
            lane=LANE_VN_BRANCH,
            metadata=metadata_overlay,
            set_active=False,
        )
        if created:
            return branch_world.snapshot(), True
        # Fallback to ensure path if fork returned existing entry.
        branch_world = WORLDLINES.ensure(branch_id)

    merged_metadata = _merge_metadata(branch_world.metadata, metadata_overlay)
    branch_world.update(
        label=branch_label,
        metadata=merged_metadata,
        lane=LANE_VN_BRANCH,
    )
    return branch_world.snapshot(), False


@router.get("/templates")
def list_theme_templates() -> Dict[str, Any]:
    _require_enabled()
    template_ids = available_templates()
    catalog = available_templates(detailed=True)
    return {
        "ok": True,
        "data": {
            "templates": template_ids,
            "catalog": catalog,
            "count": len(template_ids),
        },
    }


@router.post("/preview")
async def preview_theme(payload: ThemePreviewPayload) -> Dict[str, Any]:
    _require_enabled()
    try:
        plan_delta = _build_plan_payload(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guardrail
        LOGGER.warning("Theme preview failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Unable to build theme plan: {exc}"
        )

    templates = available_templates(detailed=True)
    response = ThemePreviewResponse(plan_delta=plan_delta, templates=templates)

    _emit_hook(
        "on_theme_preview",
        {
            "theme": plan_delta.get("theme"),
            "theme_label": plan_delta.get("theme_label"),
            "subtype": plan_delta.get("metadata", {}).get("subtype"),
            "variant": plan_delta.get("metadata", {}).get("variant"),
            "anchors_preserved": plan_delta.get("metadata", {}).get(
                "anchors_preserved", []
            ),
            "plan": plan_delta,
            "scene": payload.scene,
            "timestamp": _utc_timestamp(),
        },
    )

    return {"ok": True, "data": response.model_dump()}


@router.post("/apply")
async def apply_theme(payload: ThemeApplyPayload) -> Dict[str, Any]:
    _require_enabled()
    try:
        plan_delta = _build_plan_payload(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guardrail
        LOGGER.warning("Theme apply plan failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Unable to build theme plan: {exc}"
        )

    try:
        branch_snapshot, branch_created = _create_theme_branch(plan_delta, payload)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guardrail
        LOGGER.error("Theme branch create failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Unable to create theme branch: {exc}"
        )

    templates = available_templates(detailed=True)
    response = ThemeApplyResponse(
        plan_delta=plan_delta,
        templates=templates,
        branch=branch_snapshot,
        branch_created=branch_created,
    )

    _emit_hook(
        "on_theme_apply",
        {
            "theme": plan_delta.get("theme"),
            "theme_label": plan_delta.get("theme_label"),
            "subtype": plan_delta.get("metadata", {}).get("subtype"),
            "variant": plan_delta.get("metadata", {}).get("variant"),
            "anchors_preserved": plan_delta.get("metadata", {}).get(
                "anchors_preserved", []
            ),
            "plan": plan_delta,
            "branch": branch_snapshot,
            "branch_created": branch_created,
            "checksum": plan_delta.get("checksum"),
            "scene": payload.scene,
            "timestamp": _utc_timestamp(),
        },
    )

    return {"ok": True, "data": response.model_dump()}


__all__ = [
    "router",
    "ThemeApplyPayload",
    "ThemeApplyResponse",
    "ThemePreviewPayload",
    "ThemePreviewResponse",
]
