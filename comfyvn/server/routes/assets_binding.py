"""
Asset binding endpoints for persona portrait management.

These routes surface the helpers in ``comfyvn.vn.binding`` so that the
Studio web UI (and automation) can ensure persona portraits exist and
keep project JSON in sync with the asset registry.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.vn.binding import (
    PersonaBindingError,
    PortraitResult,
    ensure_portrait,
    link_personas,
)

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assets", tags=["Assets", "VN"])


class PortraitBindingPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    personaId: str = Field(alias="personaId")
    path: str
    style: str
    sidecar: Optional[str] = None
    registryUid: Optional[str] = Field(default=None, alias="registryUid")
    expressionMap: Dict[str, str]
    placeholder: bool = False
    projectId: Optional[str] = Field(default=None, alias="projectId")
    meta: Dict[str, Any] = Field(default_factory=dict)


class EnsurePortraitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    personaId: str = Field(
        ..., description="Persona identifier to bind.", alias="personaId"
    )
    style: Optional[str] = Field(
        default=None,
        description="Optional portrait style override; falls back to 'default'.",
    )
    projectId: Optional[str] = Field(
        default=None,
        description="Optional project scope to attribute the asset registry entry.",
        alias="projectId",
    )
    force: bool = Field(
        default=False,
        description="If true, re-render the portrait even if an asset already exists.",
    )


class EnsurePortraitResponse(BaseModel):
    ok: bool = True
    data: PortraitBindingPayload


class LinkPersonaRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    projectId: str = Field(
        ..., description="Project identifier to scan.", alias="projectId"
    )
    personaId: Optional[str] = Field(
        default=None,
        description="Optional persona id to restrict binding; processes all when omitted.",
        alias="personaId",
    )
    style: Optional[str] = Field(
        default=None,
        description="Optional style override applied to all processed personas.",
    )
    force: bool = Field(
        default=False,
        description="Force regeneration even if persona already references an asset.",
    )


class LinkPersonaData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    projectId: str = Field(alias="projectId")
    items: List[PortraitBindingPayload]
    count: int


class LinkPersonaResponse(BaseModel):
    ok: bool = True
    data: LinkPersonaData


def _result_to_payload(result: PortraitResult) -> PortraitBindingPayload:
    return PortraitBindingPayload.model_validate(result.as_dict())


@router.post(
    "/ensure/portrait",
    response_model=EnsurePortraitResponse,
    summary="Ensure a persona portrait asset exists.",
)
def api_ensure_portrait(
    payload: EnsurePortraitRequest = Body(...),
) -> EnsurePortraitResponse:
    try:
        result = ensure_portrait(
            payload.personaId,
            style=payload.style,
            project_id=payload.projectId,
            force=payload.force,
        )
    except ValueError as exc:
        LOGGER.debug("ensure_portrait rejected payload: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PersonaBindingError as exc:
        LOGGER.debug("ensure_portrait failed: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("ensure_portrait crashed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Unable to ensure portrait."
        ) from exc
    return EnsurePortraitResponse(data=_result_to_payload(result))


@router.post(
    "/link_persona",
    response_model=LinkPersonaResponse,
    summary="Ensure personas within a project have portrait bindings.",
)
def api_link_persona(payload: LinkPersonaRequest = Body(...)) -> LinkPersonaResponse:
    try:
        results = link_personas(
            payload.projectId,
            persona_id=payload.personaId,
            style=payload.style,
            force=payload.force,
        )
    except ValueError as exc:
        LOGGER.debug("link_personas invalid project: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PersonaBindingError as exc:
        LOGGER.debug("link_personas failed: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("link_personas crashed: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to link personas.") from exc

    payloads = [_result_to_payload(result) for result in results]
    data = LinkPersonaData(
        projectId=payload.projectId,
        items=payloads,
        count=len(payloads),
    )
    return LinkPersonaResponse(data=data)
