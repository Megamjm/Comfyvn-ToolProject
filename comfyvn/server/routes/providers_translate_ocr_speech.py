from __future__ import annotations

"""
Public translation, OCR, and speech provider registry + dry-run helpers.
"""

from typing import Any, Callable, Dict, Iterable, Mapping, Sequence

from fastapi import APIRouter, Body

from comfyvn.config import feature_flags
from comfyvn.public_providers import (
    catalog,
    ocr_aws_rekognition,
    ocr_google_vision,
    speech_assemblyai,
    speech_deepgram,
    translate_aws,
    translate_deepl,
    translate_google,
)

router = APIRouter(
    prefix="/api/providers/translate",
    tags=["Translation/OCR/Speech Providers (public)"],
)

FEATURE_FLAG = "enable_public_translate"


def _feature_context() -> Dict[str, Any]:
    enabled = feature_flags.is_enabled(FEATURE_FLAG)
    return {"feature": FEATURE_FLAG, "enabled": enabled}


def _merge_entry(module: Any, service: str) -> Dict[str, Any]:
    entry = module.registry_entry()
    health = module.health()
    merged = dict(entry)
    merged["service"] = service
    merged["credentials_present"] = bool(health.get("ok"))
    merged["links"] = {
        "docs": entry.get("docs_url"),
        "pricing": entry.get("pricing_url"),
    }
    merged["last_checked"] = health.get("last_checked") or entry.get("last_checked")
    merged["health"] = {
        key: value
        for key, value in health.items()
        if key not in {"provider", "docs_url", "pricing_url", "last_checked"}
    }
    return merged


def _translate_registry() -> Dict[str, Sequence[Dict[str, Any]]]:
    return {
        "translate": [
            _merge_entry(translate_google, "translate"),
            _merge_entry(translate_deepl, "translate"),
            _merge_entry(translate_aws, "translate"),
        ],
        "ocr": [
            _merge_entry(ocr_google_vision, "ocr"),
            _merge_entry(ocr_aws_rekognition, "ocr"),
        ],
        "speech": [
            _merge_entry(speech_deepgram, "speech"),
            _merge_entry(speech_assemblyai, "speech"),
        ],
    }


@router.get("/health", summary="Translation/OCR/speech provider registry")
async def translate_health() -> Dict[str, Any]:
    feature = _feature_context()
    registry = _translate_registry()
    return {
        "ok": feature["enabled"],
        "feature": feature,
        "providers": registry,
        "pricing_links": {
            "google_translate": translate_google.registry_entry().get("pricing_url"),
            "deepl": translate_deepl.registry_entry().get("pricing_url"),
            "amazon_translate": translate_aws.registry_entry().get("pricing_url"),
            "google_vision": ocr_google_vision.registry_entry().get("pricing_url"),
            "aws_rekognition": ocr_aws_rekognition.registry_entry().get("pricing_url"),
            "deepgram": speech_deepgram.registry_entry().get("pricing_url"),
            "assemblyai": speech_assemblyai.registry_entry().get("pricing_url"),
        },
    }


@router.get("/public/catalog", summary="List translation/OCR/speech providers")
async def translate_catalog() -> Dict[str, Any]:
    return {
        "ok": True,
        "feature": _feature_context(),
        "providers": catalog.catalog_for("translate_ocr_speech"),
    }


def _resolve_texts(payload: Mapping[str, Any]) -> Iterable[str]:
    raw_texts = payload.get("texts") or payload.get("text")
    if isinstance(raw_texts, str):
        return [raw_texts]
    if isinstance(raw_texts, Iterable):
        return [str(item) for item in raw_texts]
    return []


def _resolve_cfg(payload: Mapping[str, Any]) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    raw_cfg = payload.get("config") or payload.get("cfg")
    if isinstance(raw_cfg, Mapping):
        cfg = dict(raw_cfg)
    return cfg


def _translation_dry_run(
    adapter: Any,
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    if hasattr(adapter, "dry_run_payload"):
        return adapter.dry_run_payload(texts, source, target, cfg)  # type: ignore[attr-defined]
    translated = adapter.translate(texts, source, target, cfg)  # type: ignore[attr-defined]
    return {
        "provider": getattr(adapter, "PROVIDER_ID", "unknown"),
        "dry_run": True,
        "items": [
            {"src": src, "tgt": tgt, "source_lang": source, "target_lang": target}
            for src, tgt in zip(texts, translated)
        ],
    }


def _dispatch_translation(
    provider_id: str,
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    provider_map: Dict[
        str,
        Callable[[Iterable[str], str, str, Mapping[str, Any] | None], Dict[str, Any]],
    ] = {
        "google_translate": lambda a, b, c, d: _translation_dry_run(
            translate_google, a, b, c, d
        ),
        "deepl": lambda a, b, c, d: _translation_dry_run(translate_deepl, a, b, c, d),
        "amazon_translate": lambda a, b, c, d: _translation_dry_run(
            translate_aws, a, b, c, d
        ),
    }
    runner = provider_map.get(provider_id.lower())
    if not runner:
        return {
            "ok": False,
            "dry_run": True,
            "reason": f"provider '{provider_id}' unsupported",
        }
    result = runner(list(texts), source, target, cfg)
    result.setdefault("dry_run", True)
    result.setdefault("provider", provider_id.lower())
    result["ok"] = True
    return result


@router.post(
    "/public/translate",
    summary="Dry-run translation payload for the requested provider",
)
async def translate_dry_run(
    payload: Mapping[str, Any] = Body(default_factory=dict),
) -> Dict[str, Any]:
    provider = str(payload.get("provider") or payload.get("id") or "google_translate")
    source = str(payload.get("source") or payload.get("src") or "auto")
    target = str(payload.get("target") or payload.get("dest") or "en")
    texts = list(_resolve_texts(payload))
    cfg = _resolve_cfg(payload)
    feature = _feature_context()
    result = _dispatch_translation(provider, texts, source, target, cfg)
    result["feature"] = feature
    if not feature["enabled"]:
        result.setdefault("ok", False)
        result.setdefault("reason", "feature disabled")
    return result


__all__ = ["router"]
