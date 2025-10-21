from typing import Any, Dict

from fastapi import APIRouter
from PySide6.QtGui import QAction

from comfyvn.modules.orchestration.pipeline_manager import (PipelineContext,
                                                            PipelineManager)

router = APIRouter()


@router.post("/character")
async def render_character(payload: Dict[str, Any]):
    pm = PipelineManager(PipelineContext())
    return pm.render_character_with_progress(payload)
