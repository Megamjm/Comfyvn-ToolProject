from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.themes import available_templates
from comfyvn.themes import plan as plan_theme

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/themes", tags=["Themes"])

FEATURE_FLAG = "enable_themes"


def _require_enabled() -> None:
    if not feature_flags.is_enabled(FEATURE_FLAG):
        raise HTTPException(status_code=403, detail=f"{FEATURE_FLAG} disabled")


class ThemeApplyPayload(BaseModel):
    theme: str = Field(
        ..., description="Theme identifier (Modern, Fantasy, Romantic, Dark, Action)."
    )
    scene: Dict[str, Any] = Field(
        default_factory=dict, description="Optional scene or world state snapshot."
    )
    overrides: Dict[str, Any] | None = Field(
        default=None,
        description="Optional overrides, e.g. {'characters': {'alice': {...}}}.",
    )

    model_config = ConfigDict(extra="allow")


class ThemeApplyResponse(BaseModel):
    plan_delta: Dict[str, Any]
    templates: list[str]

    model_config = ConfigDict(extra="allow")


@router.get("/templates")
def list_theme_templates() -> Dict[str, Any]:
    _require_enabled()
    templates = available_templates()
    return {"ok": True, "data": {"templates": templates, "count": len(templates)}}


@router.post("/apply")
async def apply_theme(payload: ThemeApplyPayload) -> Dict[str, Any]:
    _require_enabled()
    try:
        plan_delta = plan_theme(
            payload.theme, payload.scene, overrides=payload.overrides
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guardrail
        LOGGER.warning("Theme plan generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Unable to build theme plan: {exc}"
        )

    response = ThemeApplyResponse(
        plan_delta=plan_delta,
        templates=available_templates(),
    )
    return {"ok": True, "data": response.model_dump()}


__all__ = ["router", "ThemeApplyPayload", "ThemeApplyResponse"]
