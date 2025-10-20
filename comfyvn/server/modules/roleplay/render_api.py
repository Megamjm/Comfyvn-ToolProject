from PySide6.QtGui import QAction
from typing import Dict, Any
from fastapi import APIRouter
from comfyvn.modules.orchestration.pipeline_manager import PipelineManager, PipelineContext
router = APIRouter()
@router.post('/character')
async def render_character(payload: Dict[str, Any]):
    pm = PipelineManager(PipelineContext()); return pm.render_character_with_progress(payload)