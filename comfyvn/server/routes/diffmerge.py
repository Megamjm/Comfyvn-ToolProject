from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.diffmerge import (
    build_worldline_graph,
    diff_worldline_scenes,
    preview_worldline_merge,
)
from comfyvn.pov.timeline_worlds import merge_worlds
from comfyvn.pov.worldlines import WORLDLINES

router = APIRouter(prefix="/api/diffmerge", tags=["Diff & Merge"])

LOGGER = logging.getLogger(__name__)


class SceneDiffRequest(BaseModel):
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    mask_pov: bool = Field(default=True)
    scenario: Optional[Dict[str, Any]] = Field(default=None)

    model_config = ConfigDict(extra="ignore")


class GraphRequest(BaseModel):
    target: Optional[str] = Field(default=None)
    worlds: Optional[list[str]] = Field(default=None)
    include_fast_forward: bool = Field(default=True)

    model_config = ConfigDict(extra="ignore")


class MergeRequest(BaseModel):
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    apply: bool = Field(default=False)

    model_config = ConfigDict(extra="ignore")


def _ensure_enabled() -> None:
    if feature_flags.is_enabled("enable_diffmerge_tools", default=False):
        return
    raise HTTPException(status_code=403, detail="diffmerge tooling disabled")


@router.post("/scene")
async def worldline_scene_diff(payload: SceneDiffRequest) -> Dict[str, Any]:
    _ensure_enabled()
    result = diff_worldline_scenes(
        payload.source.strip(),
        payload.target.strip(),
        registry=WORLDLINES,
        mask_by_pov=payload.mask_pov,
        scenario=payload.scenario,
    )
    LOGGER.info(
        "Worldline diff computed",
        extra={
            "diff_source": payload.source,
            "diff_target": payload.target,
            "diff_changed_nodes": len(result["node_changes"]["changed"]),
        },
    )
    modder_hooks.emit(
        "on_worldline_diff",
        {
            "source": payload.source,
            "target": payload.target,
            "mask_pov": payload.mask_pov,
            "node_changes": result["node_changes"],
            "choice_changes": result["choice_changes"],
            "timestamp": time.time(),
        },
    )
    return result


@router.post("/worldlines/graph")
async def worldline_graph(
    payload: GraphRequest = Body(GraphRequest()),
) -> Dict[str, Any]:
    _ensure_enabled()
    result = build_worldline_graph(
        target=(payload.target.strip() if payload.target else None),
        world_ids=payload.worlds,
        registry=WORLDLINES,
        include_fast_forward=payload.include_fast_forward,
    )
    LOGGER.info(
        "Worldline graph compiled",
        extra={
            "graph_target": (
                payload.target or result.get("target", {}).get("id")
                if isinstance(result.get("target"), dict)
                else None
            ),
            "graph_world_count": len(result.get("worlds") or []),
            "graph_node_count": len(result.get("graph", {}).get("nodes") or []),
        },
    )
    return result


@router.post("/worldlines/merge")
async def worldline_merge(payload: MergeRequest) -> Dict[str, Any]:
    _ensure_enabled()
    if payload.apply:
        result = merge_worlds(
            payload.source.strip(),
            payload.target.strip(),
            registry=WORLDLINES,
            apply=True,
        )
    else:
        result = preview_worldline_merge(
            payload.source.strip(),
            payload.target.strip(),
            registry=WORLDLINES,
        )
    hook_payload = {
        "source": payload.source,
        "target": payload.target,
        "apply": payload.apply,
        "fast_forward": result.get("fast_forward"),
        "added_nodes": result.get("added_nodes", []),
        "timestamp": time.time(),
    }
    if not result.get("ok"):
        hook_payload["conflicts"] = result.get("conflicts", [])
        modder_hooks.emit("on_worldline_merge", hook_payload)
        raise HTTPException(status_code=409, detail=result)

    LOGGER.info(
        "Worldline merge %s",
        "applied" if payload.apply else "preview",
        extra={
            "merge_source": payload.source,
            "merge_target": payload.target,
            "merge_fast_forward": result.get("fast_forward"),
            "merge_added_nodes": len(result.get("added_nodes") or []),
            "merge_apply": payload.apply,
        },
    )
    modder_hooks.emit(
        "on_worldline_merge",
        hook_payload,
    )
    return result


__all__ = ["router"]
