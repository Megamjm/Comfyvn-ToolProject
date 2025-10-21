"""
Translation API routes for language management and stubbed batch translate.
"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Body, HTTPException

from comfyvn.translation import get_manager

router = APIRouter(prefix="/api", tags=["Translation"])


def _coerce_strings(payload: Any) -> List[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload if item is not None]
    if isinstance(payload, dict):
        raw_strings = payload.get("strings")
        if isinstance(raw_strings, list):
            return [str(item) for item in raw_strings if item is not None]
    raise HTTPException(
        status_code=400, detail="payload must be a list or object with 'strings'"
    )


@router.post("/translate/batch")
async def translate_batch(body: Any = Body(...)) -> dict[str, Any]:
    manager = get_manager()
    strings = _coerce_strings(body)
    target = ""
    if isinstance(body, dict):
        target = str(body.get("target") or manager.get_active_language())
    else:
        target = manager.get_active_language()
    items = manager.batch_identity(strings)
    return {"ok": True, "target": target, "items": items}


@router.get("/i18n/lang")
async def get_language() -> dict[str, Any]:
    manager = get_manager()
    return {
        "ok": True,
        "active": manager.get_active_language(),
        "fallback": manager.get_fallback_language(),
        "available": manager.available_languages(),
    }


@router.post("/i18n/lang")
async def set_language(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not isinstance(payload, dict):  # defensive; FastAPI enforces dict
        raise HTTPException(status_code=400, detail="payload must be an object")

    manager = get_manager()
    lang = payload.get("lang")
    fallback = payload.get("fallback")

    if lang is None and fallback is None:
        raise HTTPException(status_code=400, detail="lang or fallback is required")

    updated = {}
    try:
        if lang is not None:
            updated["active"] = manager.set_active_language(str(lang))
        if fallback is not None:
            updated["fallback"] = manager.set_fallback_language(str(fallback))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, **updated}
