from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException


class PipelineContext:
    """Placeholder orchestration context."""

    def __init__(self, **options: Any) -> None:
        self.options = options


class PipelineManager:
    """Placeholder pipeline manager keeping legacy endpoints alive."""

    def __init__(self, context: PipelineContext | None = None) -> None:
        self.context = context or PipelineContext()

    def render_character_with_progress(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise HTTPException(
            status_code=501,
            detail="Character rendering pipeline not configured. "
            "Install comfyvn-orchestration modules to enable render endpoints.",
        )
