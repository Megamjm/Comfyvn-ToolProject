"""
Translation API routes for language management, translation memory batching,
review workflows, and live language switching.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse

from comfyvn.translation import get_manager
from comfyvn.translation.tm_store import get_store

router = APIRouter(prefix="/api", tags=["Translation"])


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _safe_meta(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): copy.deepcopy(val) for key, val in value.items() if key is not None
    }


def _merge_meta(*metas: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for meta in metas:
        for key, value in meta.items():
            merged[str(key)] = copy.deepcopy(value)
    return merged


def _normalise_lang_param(lang: Optional[str]) -> Optional[str]:
    if lang is None:
        return None
    value = str(lang).strip()
    return value.lower() if value else None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise HTTPException(status_code=400, detail="reviewed must be a boolean value")


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="confidence must be numeric"
        ) from exc


def _coerce_limit(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="limit must be a non-negative integer"
        ) from exc
    if parsed < 0:
        raise HTTPException(
            status_code=400, detail="limit must be a non-negative integer"
        )
    return parsed


def _coerce_batch_entry(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, Mapping):
        key_candidate = (
            entry.get("key")
            or entry.get("id")
            or entry.get("uid")
            or entry.get("src")
            or entry.get("name")
        )
        source_text = (
            entry.get("source")
            or entry.get("text")
            or entry.get("default")
            or entry.get("fallback")
            or entry.get("value")
        )
        key = str(key_candidate or source_text or "").strip()
        if not key:
            raise HTTPException(
                status_code=400, detail="batch items require a 'key' field"
            )
        meta = _safe_meta(entry.get("meta"))
        for extra in ("asset", "component", "context", "scope", "domain", "scene"):
            if extra in entry and extra not in meta:
                meta[extra] = copy.deepcopy(entry[extra])
        if "hooks" in entry and "hooks" not in meta:
            hooks = entry.get("hooks")
            if isinstance(hooks, Mapping):
                meta["hooks"] = _safe_meta(hooks)
        return {
            "key": key,
            "source": str(source_text or key),
            "meta": meta,
        }
    if isinstance(entry, str):
        value = entry.strip()
        if not value:
            raise HTTPException(
                status_code=400, detail="batch items cannot be empty strings"
            )
        return {"key": value, "source": value, "meta": {}}
    if entry is None:
        raise HTTPException(
            status_code=400, detail="batch items cannot contain null entries"
        )
    value = str(entry).strip()
    if not value:
        raise HTTPException(status_code=400, detail="batch items require a key")
    return {"key": value, "source": value, "meta": {}}


def _parse_batch_payload(body: Any) -> Tuple[
    List[Dict[str, Any]],
    Optional[str],
    Optional[str],
    Dict[str, Any],
]:
    target_lang: Optional[str] = None
    source_lang: Optional[str] = None
    shared_meta: Dict[str, Any] = {}
    raw_items: Any = body

    if isinstance(body, Mapping):
        target_lang = body.get("target")
        source_lang = (
            body.get("source")
            or body.get("source_lang")
            or body.get("fallback")
            or body.get("fallback_lang")
        )
        shared_meta = _safe_meta(body.get("meta"))
        candidate = body.get("items")
        if candidate is None and "strings" in body:
            candidate = body["strings"]
        raw_items = candidate

    if not isinstance(raw_items, list):
        raise HTTPException(
            status_code=400,
            detail="payload must provide a list or an object with 'items'/'strings'",
        )

    items = [_coerce_batch_entry(entry) for entry in raw_items]
    return items, target_lang, source_lang, shared_meta


def _format_store_entry(
    entry: Mapping[str, Any],
    *,
    include_meta: bool,
    origin_override: Optional[str] = None,
    source_override: Optional[str] = None,
    source_lang: Optional[str] = None,
    fallback_text: Optional[str] = None,
    status: Optional[str] = None,
    meta_override: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    source_value = (
        source_override if source_override is not None else entry.get("source")
    )
    target_value = entry.get("target")
    origin_value = origin_override or entry.get("origin", "tm")
    data: Dict[str, Any] = {
        "id": entry.get("id"),
        "key": entry.get("key"),
        "lang": entry.get("lang"),
        "origin": origin_value,
        "source": origin_value,
        "source_text": source_value,
        "target": target_value,
        "confidence": float(entry.get("confidence", 0.0) or 0.0),
        "reviewed": bool(entry.get("reviewed", False)),
        "version": entry.get("version", 1),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "hits": entry.get("hits"),
        "reviewed_at": entry.get("reviewed_at"),
        "reviewed_by": entry.get("reviewed_by"),
    }
    data["src"] = source_value
    data["tgt"] = target_value
    if source_lang:
        data["source_lang"] = source_lang
    if fallback_text is not None:
        data["fallback"] = fallback_text
    if status:
        data["status"] = status
    if include_meta:
        if meta_override is not None:
            data["meta"] = _safe_meta(meta_override)
        else:
            data["meta"] = _safe_meta(entry.get("meta"))

    key = data.get("key")
    lang = data.get("lang")
    if key and lang:
        data["links"] = {
            "review": _link("/api/translate/review", lang=lang, key=key),
            "export_json": _link("/api/translate/export/json", lang=lang, key=key),
            "export_po": _link("/api/translate/export/po", lang=lang, key=key),
        }
    return data


def _build_review_payload(
    *,
    lang: Optional[str],
    status: str,
    key: Optional[str],
    limit: Optional[int],
    include_meta: bool,
    meta_filters: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    store = get_store()
    status_value = status.lower()
    if status_value not in {"pending", "reviewed", "all"}:
        raise HTTPException(
            status_code=400, detail="status must be 'pending', 'reviewed', or 'all'"
        )
    lang_normalised = _normalise_lang_param(lang)
    limit_value = _coerce_limit(limit) if limit is not None else None

    meta_filter = meta_filters or {}
    pending_items: List[Dict[str, Any]] = []
    reviewed_items: List[Dict[str, Any]] = []

    if status_value in {"pending", "all"}:
        pending_items = store.pending(
            lang=lang_normalised,
            key=key,
            limit=None if status_value == "all" else limit_value,
            meta_contains=meta_filter or None,
            include_meta=include_meta,
        )
    if status_value in {"reviewed", "all"}:
        reviewed_items = store.reviewed(
            lang=lang_normalised,
            key=key,
            limit=None if status_value == "all" else limit_value,
            meta_contains=meta_filter or None,
            include_meta=include_meta,
        )

    formatted: List[Dict[str, Any]] = []
    if status_value in {"pending", "all"}:
        formatted.extend(
            [
                _format_store_entry(
                    item,
                    include_meta=include_meta,
                    source_lang=None,
                    status="pending",
                )
                for item in pending_items
            ]
        )
    if status_value in {"reviewed", "all"}:
        formatted.extend(
            [
                _format_store_entry(
                    item,
                    include_meta=include_meta,
                    source_lang=None,
                    status="reviewed",
                )
                for item in reviewed_items
            ]
        )

    if status_value == "all" and limit_value is not None:
        formatted = formatted[:limit_value]

    stats = store.stats()
    pending_total = (
        stats["pending"].get(lang_normalised, 0)
        if lang_normalised
        else sum(stats["pending"].values())
    )
    reviewed_total = (
        stats["reviewed"].get(lang_normalised, 0)
        if lang_normalised
        else sum(stats["reviewed"].values())
    )
    counts = {
        "pending": len(pending_items) if status_value != "reviewed" else pending_total,
        "reviewed": (
            len(reviewed_items) if status_value != "pending" else reviewed_total
        ),
    }

    payload: Dict[str, Any] = {
        "ok": True,
        "status": status_value,
        "items": formatted,
        "counts": counts,
        "totals": stats,
        "links": {
            "export_json": _link(
                "/api/translate/export/json", lang=lang_normalised, key=key
            ),
            "export_po": _link(
                "/api/translate/export/po", lang=lang_normalised, key=key
            ),
            "batch": "/api/translate/batch",
        },
    }
    if lang_normalised:
        payload["lang"] = lang_normalised
    if key:
        payload["key"] = key
    if meta_filter:
        payload["filters"] = meta_filter
    return payload


def _apply_review_update(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=400, detail="payload must be an object")

    manager = get_manager()
    store = get_store()

    lang = payload.get("lang") or payload.get("language")
    lang_normalised = _normalise_lang_param(lang) or manager.get_active_language()
    key = payload.get("key")
    entry_id = payload.get("id") or payload.get("entry_id")

    if not entry_id:
        if not key:
            raise HTTPException(
                status_code=400, detail="id or (lang, key) pair required"
            )
        lookup = store.lookup(str(key), lang_normalised, include_meta=True)
        if not lookup:
            raise HTTPException(status_code=404, detail="translation entry not found")
        entry_id = lookup["id"]

    translation = payload.get("translation")
    if translation is None:
        translation = payload.get("target")

    reviewer = (
        payload.get("reviewer") or payload.get("reviewed_by") or payload.get("editor")
    )
    confidence = _coerce_optional_float(payload.get("confidence"))
    reviewed_flag = _coerce_optional_bool(payload.get("reviewed"))
    action = str(payload.get("action") or "").strip().lower()
    if action == "unapprove":
        reviewed_flag = False
    elif action == "approve":
        reviewed_flag = True

    meta = _safe_meta(payload.get("meta"))
    source_text = payload.get("source") or payload.get("source_text")
    origin = payload.get("origin") or ("review" if translation is not None else None)

    try:
        updated = store.approve(
            str(entry_id),
            translation=str(translation) if translation is not None else None,
            reviewer=str(reviewer) if reviewer else None,
            confidence=confidence,
            meta=meta or None,
            reviewed=reviewed_flag,
            origin=str(origin) if origin else None,
            source_text=str(source_text) if source_text is not None else None,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="translation entry not found"
        ) from exc

    source_lang = (
        payload.get("source_lang")
        or payload.get("fallback_lang")
        or manager.get_fallback_language()
    )
    fallback_text = (
        manager.get_table_value(updated.get("key", ""), source_lang)
        if source_lang and updated.get("key")
        else None
    )

    status_flag = "reviewed" if bool(updated.get("reviewed")) else "pending"
    formatted = _format_store_entry(
        updated,
        include_meta=True,
        source_override=source_text if source_text is not None else None,
        source_lang=source_lang,
        fallback_text=fallback_text,
        status=status_flag,
    )
    formatted["lang"] = updated.get("lang", lang_normalised)

    return {
        "ok": True,
        "entry": formatted,
        "links": formatted.get("links"),
    }


def _link(path: str, **params: Optional[str]) -> str:
    cleaned = {key: str(value) for key, value in params.items() if value}
    if not cleaned:
        return path
    return f"{path}?{urlencode(cleaned)}"


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #
@router.post("/translate/batch")
async def translate_batch(body: Any = Body(...)) -> dict[str, Any]:
    manager = get_manager()
    store = get_store()
    items, target_override, source_override, shared_meta = _parse_batch_payload(body)

    target_lang = (
        _normalise_lang_param(target_override) or manager.get_active_language()
    )
    target_lang = target_lang or manager.get_fallback_language() or "en"
    source_lang = (
        _normalise_lang_param(source_override)
        or manager.get_fallback_language()
        or target_lang
    )

    results: List[Dict[str, Any]] = []
    cache_hits = 0
    stubbed = 0

    for item in items:
        key = item["key"]
        per_item_meta = _safe_meta(item.get("meta"))
        merged_meta = _merge_meta(shared_meta, per_item_meta)

        fallback_text = (
            manager.get_table_value(key, source_lang) or item.get("source") or key
        )
        source_text = item.get("source") or fallback_text or key

        entry = store.lookup(key, target_lang, include_meta=True)
        status = "cached"
        origin_override = None
        if entry is None:
            entry = store.record(
                key=key,
                lang=target_lang,
                source_text=source_text,
                target_text=source_text,
                origin="stub",
                confidence=0.35,
                reviewed=False,
                meta=merged_meta or None,
            )
            stubbed += 1
            status = "stubbed"
            origin_override = "stub"
        else:
            cache_hits += 1
            if entry.get("origin") == "stub":
                origin_override = "tm"

        entry_meta = _safe_meta(entry.get("meta"))
        if merged_meta:
            entry_meta = _merge_meta(entry_meta, merged_meta)

        formatted = _format_store_entry(
            entry,
            include_meta=True,
            origin_override=origin_override,
            source_override=source_text,
            source_lang=source_lang,
            fallback_text=fallback_text,
            status=status if entry.get("reviewed") else "pending",
            meta_override=entry_meta,
        )
        results.append(formatted)

    return {
        "ok": True,
        "target": target_lang,
        "source_lang": source_lang,
        "items": results,
        "links": {
            "review": _link(
                "/api/translate/review", lang=target_lang, status="pending"
            ),
            "export_json": _link("/api/translate/export/json", lang=target_lang),
            "export_po": _link("/api/translate/export/po", lang=target_lang),
        },
        "debug": {
            "requested": len(items),
            "cache_hits": cache_hits,
            "stubbed": stubbed,
            "available_languages": manager.available_languages(),
        },
    }


@router.get("/translate/review")
async def get_review_entries(
    lang: str | None = Query(default=None),
    status: str = Query(default="pending"),
    key: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    include_meta: bool = Query(default=False),
    asset: str | None = Query(default=None),
    component: str | None = Query(default=None),
) -> dict[str, Any]:
    meta_filters = {}
    if asset:
        meta_filters["asset"] = asset
    if component:
        meta_filters["component"] = component
    return _build_review_payload(
        lang=lang,
        status=status,
        key=key,
        limit=limit,
        include_meta=_as_bool(include_meta, False),
        meta_filters=meta_filters or None,
    )


@router.post("/translate/review")
async def post_review_entry(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _apply_review_update(payload)


@router.get("/translate/review/pending")
async def get_review_queue(lang: str | None = Query(default=None)) -> dict[str, Any]:
    payload = _build_review_payload(
        lang=lang,
        status="pending",
        key=None,
        limit=None,
        include_meta=True,
        meta_filters=None,
    )
    items = payload["items"]
    by_lang: Dict[str, int] = {}
    for item in items:
        entry_lang = item.get("lang")
        if entry_lang:
            by_lang[entry_lang] = by_lang.get(entry_lang, 0) + 1
    legacy: Dict[str, Any] = {
        "ok": True,
        "items": items,
        "total": len(items),
        "by_lang": by_lang,
    }
    if lang:
        legacy["lang"] = _normalise_lang_param(lang)
    return legacy


@router.post("/translate/review/approve")
async def approve_translation(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    merged_payload = dict(payload)
    merged_payload.setdefault("action", "approve")
    result = _apply_review_update(merged_payload)
    return {"ok": True, "entry": result["entry"]}


@router.get("/translate/export/json")
async def export_tm_json(
    lang: str | None = Query(default=None),
    key: str | None = Query(default=None),
    include_meta: bool = Query(default=False),
) -> dict[str, Any]:
    store = get_store()
    payload = store.export_json(
        lang=_normalise_lang_param(lang),
        key=key,
        include_meta=_as_bool(include_meta, False),
    )
    payload["ok"] = True
    return payload


@router.get("/translate/export/po")
async def export_tm_po(
    lang: str | None = Query(default=None),
    key: str | None = Query(default=None),
    include_meta: bool = Query(default=False),
) -> PlainTextResponse:
    store = get_store()
    lang_normalised = _normalise_lang_param(lang)
    po_text = store.export_po(
        lang=lang_normalised,
        key=key,
        include_meta=_as_bool(include_meta, False),
    )
    filename_parts = ["translations"]
    if lang_normalised:
        filename_parts.append(lang_normalised)
    if key:
        filename_parts.append("key")
    filename = "_".join(filename_parts) + ".po"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return PlainTextResponse(
        po_text, media_type="text/x-gettext-translation", headers=headers
    )


@router.get("/i18n/lang")
async def get_language() -> dict[str, Any]:
    manager = get_manager()
    active = manager.get_active_language()
    fallback = manager.get_fallback_language()
    available = manager.available_languages()
    return {
        "ok": True,
        "active": active,
        "fallback": fallback,
        "available": available,
        "links": {
            "set": "/api/i18n/lang",
            "batch": "/api/translate/batch",
            "review": "/api/translate/review",
        },
    }


@router.post("/i18n/lang")
async def set_language(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
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

    updated["links"] = {
        "batch": "/api/translate/batch",
        "review": "/api/translate/review",
    }
    return {"ok": True, **updated}
