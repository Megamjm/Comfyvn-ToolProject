"""
Translation API routes for language management and stubbed batch translate.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse

from comfyvn.translation import get_manager
from comfyvn.translation.tm_store import get_store

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
    store = get_store()
    strings = _coerce_strings(body)
    target: str
    if isinstance(body, dict):
        target = str(body.get("target") or manager.get_active_language())
    else:
        target = manager.get_active_language()
    if not target:
        target = manager.get_fallback_language() or "en"
    responses: List[Dict[str, Any]] = []
    for text in strings:
        cached = store.lookup(text, target)
        if cached:
            responses.append(
                {
                    "id": cached["id"],
                    "src": text,
                    "tgt": cached["target"],
                    "lang": cached["lang"],
                    "source": "tm",
                    "confidence": float(cached.get("confidence", 1.0)),
                    "reviewed": bool(cached.get("reviewed", False)),
                }
            )
            continue

        stub_target = text
        confidence = 0.35
        recorded = store.record(
            source=text,
            target=stub_target,
            lang=target,
            confidence=confidence,
            reviewed=False,
        )
        responses.append(
            {
                "id": recorded["id"],
                "src": text,
                "tgt": stub_target,
                "lang": recorded["lang"],
                "source": "stub",
                "confidence": confidence,
                "reviewed": False,
            }
        )
    return {"ok": True, "target": target, "items": responses}


@router.get("/translate/review/pending")
async def get_review_queue(lang: str | None = Query(default=None)) -> dict[str, Any]:
    store = get_store()
    items = store.pending(lang=lang)
    by_lang: Dict[str, int] = {}
    for item in items:
        by_lang[item["lang"]] = by_lang.get(item["lang"], 0) + 1
    payload: Dict[str, Any] = {
        "ok": True,
        "items": items,
        "total": len(items),
        "by_lang": by_lang,
    }
    if lang:
        payload["lang"] = lang.strip().lower()
    return payload


@router.post("/translate/review/approve")
async def approve_translation(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not isinstance(payload, dict):  # defensive; FastAPI enforces dict
        raise HTTPException(status_code=400, detail="payload must be an object")

    entry_id = payload.get("id")
    translation = payload.get("translation")
    if translation is None:
        translation = payload.get("target")
    reviewer = payload.get("reviewed_by") or payload.get("reviewer")
    confidence = payload.get("confidence")

    store = get_store()
    identifier: str | None = None
    if entry_id:
        identifier = str(entry_id)
    else:
        lang = payload.get("lang")
        source = payload.get("source")
        if lang and source:
            cached = store.lookup(str(source), str(lang))
            if cached:
                identifier = cached["id"]
        if not identifier:
            raise HTTPException(
                status_code=400, detail="id or valid (lang, source) pair required"
            )

    try:
        updated = store.approve(
            identifier,
            translation=str(translation) if translation is not None else None,
            reviewer=str(reviewer) if reviewer else None,
            confidence=float(confidence) if confidence is not None else None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="translation entry not found")

    return {"ok": True, "entry": updated}


@router.get("/translate/export/json")
async def export_tm_json(lang: str | None = Query(default=None)) -> dict[str, Any]:
    store = get_store()
    payload = store.export_json(lang=lang)
    payload["ok"] = True
    return payload


@router.get("/translate/export/po")
async def export_tm_po(lang: str | None = Query(default=None)) -> PlainTextResponse:
    store = get_store()
    po_text = store.export_po(lang=lang)
    filename_lang = lang.strip().lower() if lang else "all"
    filename = f"translations_{filename_lang}.po"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return PlainTextResponse(
        po_text, media_type="text/x-gettext-translation", headers=headers
    )


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
