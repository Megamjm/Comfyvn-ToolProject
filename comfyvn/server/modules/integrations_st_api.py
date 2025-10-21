"""SillyTavern integration endpoints."""

from __future__ import annotations

import importlib
from fastapi import APIRouter

router = APIRouter(prefix="/integrations/st", tags=["Integrations"])


@router.get("/health", summary="SillyTavern bridge health probe")
async def st_bridge_health() -> dict[str, object]:
    status = "ok"
    details: dict[str, object] = {"module": "unavailable"}

    try:
        module = importlib.import_module("comfyvn.modules.st_bridge.extension_sync")
    except ModuleNotFoundError:
        status = "degraded"
    else:
        details.update({"module": "available", "has_main": hasattr(module, "main")})

    return {"status": status, "details": details}

