from __future__ import annotations

"""
Public LLM provider catalog.
"""

from typing import Any, Dict

from fastapi import APIRouter

from comfyvn.config import feature_flags
from comfyvn.public_providers import catalog

router = APIRouter(prefix="/api/providers/llm/public", tags=["LLM Providers (public)"])

FEATURE_FLAG = "enable_public_llm"


def _feature_context() -> Dict[str, Any]:
    return {
        "feature": FEATURE_FLAG,
        "enabled": feature_flags.is_enabled(FEATURE_FLAG),
    }


@router.get("/catalog", summary="List LLM providers with pricing heuristics")
async def llm_catalog() -> Dict[str, Any]:
    return {
        "ok": True,
        "feature": _feature_context(),
        "providers": catalog.catalog_for("llm_inference"),
    }


__all__ = ["router"]
