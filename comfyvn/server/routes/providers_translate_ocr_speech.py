from __future__ import annotations

"""
Public translation/OCR/speech provider metadata and dry-run hooks.
"""

from typing import Any, Dict, Iterable, Mapping

from fastapi import APIRouter, Body

from comfyvn.config import feature_flags
from comfyvn.public_providers import catalog, translate_google

router = APIRouter(
    prefix="/api/providers/translate/public",
    tags=["Translation/OCR/Speech Providers (public)"],
)

FEATURE_FLAG = "enable_public_translate"


def _feature_context() -> Dict[str, Any]:
    return {
        "feature": FEATURE_FLAG,
        "enabled": feature_flags.is_enabled(FEATURE_FLAG),
    }


@router.get("/catalog", summary="List translation/OCR/speech providers")
async def translate_catalog() -> Dict[str, Any]:
    return {
        "ok": True,
        "feature": _feature_context(),
        "providers": catalog.catalog_for("translate_ocr_speech"),
    }


@router.post(
    "/google/translate", summary="Dry-run translation via Google (echo without key)"
)
async def google_translate_endpoint(
    payload: Mapping[str, Any] = Body(default_factory=dict),
) -> Dict[str, Any]:
    texts: Iterable[str] = ()
    source = str(payload.get("source") or payload.get("src") or "auto")
    target = str(payload.get("target") or payload.get("dest") or "en")
    cfg: Dict[str, Any] = {}

    raw_texts = payload.get("texts") or payload.get("text")
    if isinstance(raw_texts, str):
        texts = [raw_texts]
    elif isinstance(raw_texts, Iterable):
        texts = [str(item) for item in raw_texts]

    raw_cfg = payload.get("config") or payload.get("cfg")
    if isinstance(raw_cfg, Mapping):
        cfg = dict(raw_cfg)

    translated = translate_google.translate(texts, source, target, cfg)
    return {
        "ok": True,
        "texts": list(translated),
        "feature": _feature_context(),
        "provider": "google_translate",
        "dry_run": True,
    }


__all__ = ["router"]
