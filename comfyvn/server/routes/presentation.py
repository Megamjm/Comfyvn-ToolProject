from __future__ import annotations

import logging
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.presentation.directives import (
    PresentationNode,
    SceneState,
    compile_plan,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/presentation", tags=["Presentation"])


class PlanRequest(BaseModel):
    scene_state: SceneState
    node: PresentationNode

    model_config = ConfigDict(extra="ignore")


class PlanResponse(BaseModel):
    node_id: str
    plan: List[dict[str, Any]]
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


@router.post("/plan", response_model=PlanResponse)
async def presentation_plan(payload: PlanRequest) -> PlanResponse:
    """
    Compile a presentation directive plan for the supplied node and scene state.
    """
    try:
        plan = compile_plan(payload.scene_state, payload.node)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.warning("Presentation plan compile failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Unable to compile plan: {exc}")

    response = PlanResponse(
        node_id=payload.node.id,
        plan=plan,
        meta={"count": len(plan)},
    )
    return response


__all__ = ["router", "PlanRequest", "PlanResponse"]
