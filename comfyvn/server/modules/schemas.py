from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from PySide6.QtGui import QAction


class RenderRequest(BaseModel):
    id: Optional[str] = Field(None, min_length=1, max_length=64)
    prompt: Optional[str] = Field(None, max_length=500)
    workflow: Optional[Dict[str, Any]] = None
    backend: str = Field("comfyui")
    extras: Dict[str, Any] = Field(default_factory=dict)
    depends_on: Optional[List[str]] = None
    retries: int = 0

    @field_validator("backend")
    @classmethod
    def backend_ok(cls, v):
        if v not in {"comfyui"}:
            raise ValueError("backend must be 'comfyui'")
        return v


class BatchRequest(BaseModel):
    items: List[RenderRequest]
    depends_on: Optional[List[str]] = None
    retries: int = 0


class CustomJob(BaseModel):
    type: str = Field(..., min_length=2, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)
    depends_on: Optional[List[str]] = None
    retries: int = 0
