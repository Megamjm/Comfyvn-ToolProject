from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.weather import WEATHER_PLANNER

router = APIRouter(prefix="/api/weather", tags=["Weather"])

logger = logging.getLogger(__name__)


class WeatherStateRequest(BaseModel):
    """
    Update payload for the dynamic weather planner.

    Clients may send individual fields (time_of_day/weather/ambience) or a
    nested `state` dictionary that follows the same contract.  Extra keys are
    ignored so callers can hydrate the payload directly from their form state.
    """

    time_of_day: str | None = None
    weather: str | None = None
    ambience: str | None = None
    state: Mapping[str, Any] | None = Field(default=None)

    model_config = ConfigDict(extra="ignore")


class WeatherPlanResponse(BaseModel):
    state: dict[str, Any]
    scene: dict[str, Any]
    transition: dict[str, Any]
    particles: dict[str, Any] | None = None
    sfx: dict[str, Any]
    meta: dict[str, Any]

    model_config = ConfigDict(extra="ignore")


def _ensure_mapping(value: Any, *, field: str) -> MutableMapping[str, Any]:
    if isinstance(value, MutableMapping):
        return value
    raise HTTPException(status_code=400, detail=f"{field} must be an object")


def _ensure_enabled() -> None:
    if feature_flags.is_enabled("enable_weather_overlays", default=False):
        return
    raise HTTPException(status_code=403, detail="enable_weather_overlays disabled")


@router.get("/state", response_model=WeatherPlanResponse)
async def weather_state_snapshot() -> WeatherPlanResponse:
    _ensure_enabled()
    plan = WEATHER_PLANNER.snapshot()
    return WeatherPlanResponse.model_validate(plan)


@router.post("/state", response_model=WeatherPlanResponse)
async def update_weather_state(payload: WeatherStateRequest) -> WeatherPlanResponse:
    _ensure_enabled()
    if payload.state is not None:
        merged_payload = dict(_ensure_mapping(payload.state, field="state"))
    else:
        merged_payload = payload.model_dump(
            exclude_none=True,
            exclude={"state"},
        )

    if merged_payload:
        current = WEATHER_PLANNER.snapshot()
        base_state = dict(current.get("state", {}))
        base_state.update(merged_payload)
        plan = WEATHER_PLANNER.update(base_state)
    else:
        plan = WEATHER_PLANNER.snapshot()

    response = WeatherPlanResponse.model_validate(plan)

    logger.info(
        "Weather plan updated",
        extra={
            "weather_state": response.state,
            "weather_meta": response.meta,
            "weather_transition": {
                "duration": response.transition.get("duration"),
                "exposure_shift": response.transition.get("exposure_shift"),
            },
            "weather_particles": (response.particles or {}).get("type"),
            "weather_lut": (response.scene.get("lut") or {}).get("path"),
        },
    )
    modder_hooks.emit(
        "on_weather_changed",
        {
            "state": response.state,
            "summary": response.scene.get("summary", {}),
            "transition": response.transition,
            "particles": response.particles,
            "sfx": {
                "loop": response.sfx.get("loop"),
                "gain_db": response.sfx.get("gain_db"),
                "tags": response.sfx.get("tags"),
                "fade_in": response.sfx.get("fade_in"),
                "fade_out": response.sfx.get("fade_out"),
            },
            "lut": response.scene.get("lut"),
            "bake_ready": response.scene.get("bake_ready", False),
            "flags": response.meta.get("flags", {}),
            "meta": response.meta,
            "trigger": (
                "api.weather.state.post" if merged_payload else "api.weather.state.get"
            ),
            "timestamp": response.meta.get("updated_at"),
        },
    )

    return response


__all__ = ["router", "WeatherStateRequest", "WeatherPlanResponse"]
