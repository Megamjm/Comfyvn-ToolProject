from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from comfyvn.config.feature_flags import is_enabled
from comfyvn.editor.blocking_assistant import BlockingAssistant, BlockingRequest
from comfyvn.editor.snapshot_sheet import (
    SnapshotSheetBuilder,
    SnapshotSheetRequest,
)

router = APIRouter(prefix="/api/editor", tags=["Editor"])

_BLOCKING = BlockingAssistant()
_SHEETS = SnapshotSheetBuilder()


@router.post("/blocking")
async def suggest_blocking(payload: BlockingRequest) -> Dict[str, Any]:
    if not is_enabled("enable_blocking_assistant", default=False):
        raise HTTPException(
            status_code=403, detail="enable_blocking_assistant disabled"
        )
    use_role_mapping = is_enabled("enable_llm_role_mapping", default=False)
    plan = _BLOCKING.suggest(payload, use_role_mapping=use_role_mapping)
    return plan.model_dump(mode="python")


@router.post("/snapshot_sheet")
async def render_snapshot_sheet(payload: SnapshotSheetRequest) -> Dict[str, Any]:
    if not is_enabled("enable_snapshot_sheets", default=False):
        raise HTTPException(status_code=403, detail="enable_snapshot_sheets disabled")
    try:
        result = _SHEETS.render(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump(mode="python")


__all__ = ["router"]
