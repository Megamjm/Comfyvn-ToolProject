from __future__ import annotations

"""
Public image/video provider routes.

These endpoints surface catalog metadata and accept dry-run generation payloads.
Actual network execution remains opt-in behind feature flags and credentials.
"""

import logging
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from fastapi import APIRouter, Body, HTTPException

from comfyvn.config import feature_flags
from comfyvn.core.task_registry import task_registry
from comfyvn.public_providers import (
    image_fal,
    image_stability,
    video_luma,
    video_pika,
    video_runway,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/providers",
    tags=["Public Media Providers"],
)

IMAGE_MODULES: Sequence[object] = (image_stability, image_fal)
VIDEO_MODULES: Sequence[object] = (video_runway, video_pika, video_luma)


def _aliases_for(module: object) -> Iterable[str]:
    aliases = getattr(module, "ALIASES", None)
    if not aliases:
        identifier = getattr(module, "PROVIDER_ID", None) or module.catalog_entry().get(
            "id"
        )
        return (str(identifier).lower(),)
    return tuple(str(alias).lower() for alias in aliases)


def _build_module_map(modules: Sequence[object]) -> Dict[str, object]:
    mapping: Dict[str, object] = {}
    for module in modules:
        for alias in _aliases_for(module):
            mapping[alias] = module
    return mapping


IMAGE_PROVIDER_MAP = _build_module_map(IMAGE_MODULES)
VIDEO_PROVIDER_MAP = _build_module_map(VIDEO_MODULES)


def _canonical_id(module: object) -> str:
    entry = module.catalog_entry()
    identifier = entry.get("id") or getattr(module, "PROVIDER_ID", None)
    return str(identifier or "").lower()


def _flag_name(module: object, default: str) -> str:
    flag = getattr(module, "FEATURE_FLAG", None)
    if isinstance(flag, str) and flag:
        return flag
    return default


def _env_keys(module: object) -> Sequence[str]:
    keys = getattr(module, "ENV_KEYS", ())
    return tuple(str(item) for item in keys)


def _kind(module: object, default: str) -> str:
    kind = getattr(module, "KIND", None)
    if isinstance(kind, str) and kind:
        return kind
    return default


def _flag_enabled(flag_name: str, *, kind: str) -> bool:
    if feature_flags.is_enabled(flag_name):
        return True
    if kind in {"image", "video"} and flag_name != "enable_public_image_video":
        return feature_flags.is_enabled("enable_public_image_video")
    return False


def _ensure_mapping(payload: Any, detail: str) -> MutableMapping[str, Any]:
    if isinstance(payload, MutableMapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


def _catalog_payload(
    modules: Sequence[object], *, default_flag: str, default_kind: str
) -> Dict[str, Any]:
    items: list[Dict[str, Any]] = []
    for module in modules:
        try:
            entry = dict(module.catalog_entry())
        except Exception as exc:
            LOGGER.warning("Failed to load catalog for %s: %s", module, exc)
            continue

        flag_name = _flag_name(module, default_flag)
        kind = entry.get("kind") or _kind(module, default_kind)
        flag_enabled = _flag_enabled(flag_name, kind=kind)
        try:
            credentials_present = bool(module.credentials_present())
        except Exception as exc:
            LOGGER.warning("Credential probe failed for %s: %s", module, exc)
            credentials_present = False

        status_notes: list[str]
        raw_notes = entry.get("status_notes")
        if isinstance(raw_notes, list):
            status_notes = list(raw_notes)
        elif isinstance(raw_notes, str):
            status_notes = [raw_notes]
        else:
            status_notes = []

        if not credentials_present:
            status_notes.append("missing credentials")
        if not flag_enabled:
            status_notes.append("feature flag disabled")

        entry.update(
            {
                "id": _canonical_id(module),
                "kind": kind,
                "feature_flag": flag_name,
                "feature_flag_enabled": flag_enabled,
                "credentials_present": credentials_present,
                "status": (
                    "ready" if (flag_enabled and credentials_present) else "dry-run"
                ),
                "status_notes": status_notes,
                "env_keys": list(_env_keys(module)),
                "aliases": list(_aliases_for(module)),
            }
        )
        items.append(entry)

    return {"providers": items}


@router.get("/image/catalog")
async def image_catalog() -> Dict[str, Any]:
    return _catalog_payload(
        IMAGE_MODULES,
        default_flag="enable_public_image_providers",
        default_kind="image",
    )


@router.get("/video/catalog")
async def video_catalog() -> Dict[str, Any]:
    return _catalog_payload(
        VIDEO_MODULES,
        default_flag="enable_public_video_providers",
        default_kind="video",
    )


def _resolve_module(kind: str, provider_id: str) -> object:
    mapping = IMAGE_PROVIDER_MAP if kind == "image" else VIDEO_PROVIDER_MAP
    module = mapping.get(provider_id.lower())
    if module:
        return module
    raise HTTPException(
        status_code=404, detail=f"provider '{provider_id}' not supported"
    )


def _execute_allowed(module: object) -> bool:
    kind = _kind(module, "image")
    default_flag = (
        "enable_public_image_providers"
        if kind == "image"
        else "enable_public_video_providers"
    )
    flag_name = _flag_name(module, default_flag)
    flag_enabled = _flag_enabled(flag_name, kind=kind)
    if not flag_enabled:
        return False
    try:
        return bool(module.credentials_present())
    except Exception:
        return False


def _register_job(kind: str, provider: str, result: Mapping[str, Any]) -> str:
    payload = {
        "provider": provider,
        "mode": result.get("mode"),
        "payload": result.get("payload"),
        "dry_run": bool(result.get("dry_run", True)),
        "estimates": result.get("estimates"),
    }
    message = f"{provider} {kind} request"
    job_id = task_registry.register(
        f"public.{kind}.generate",
        payload,
        message=message,
        meta={"provider": provider, "dry_run": payload["dry_run"]},
    )
    task_registry.update(
        job_id,
        status="done",
        progress=1.0,
        message=message,
    )
    return job_id


def _generate(kind: str, module: object, payload: Mapping[str, Any]) -> Dict[str, Any]:
    allow_execute = _execute_allowed(module)
    try:
        result = module.generate(payload, execute=allow_execute)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("public %s provider failed: %s", kind, exc)
        raise HTTPException(
            status_code=500, detail="provider execution failed"
        ) from exc

    canonical = _canonical_id(module)
    result.setdefault("provider", canonical)
    result.setdefault("kind", kind)
    result.setdefault("dry_run", True)
    return result


@router.post("/image/generate")
async def image_generate(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    provider_id = str(
        data.get("provider") or data.get("provider_id") or data.get("id") or ""
    ).strip()
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider is required")

    module = _resolve_module("image", provider_id)
    result = _generate("image", module, data)
    job_id = _register_job("image", result["provider"], result)
    LOGGER.info(
        "public.image.generate",
        extra={
            "provider": result["provider"],
            "dry_run": result.get("dry_run", True),
            "execution_allowed": result.get("execution_allowed", False),
        },
    )
    result["job_id"] = job_id
    return result


@router.post("/video/generate")
async def video_generate(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    provider_id = str(
        data.get("provider") or data.get("provider_id") or data.get("id") or ""
    ).strip()
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider is required")

    module = _resolve_module("video", provider_id)
    result = _generate("video", module, data)
    job_id = _register_job("video", result["provider"], result)
    LOGGER.info(
        "public.video.generate",
        extra={
            "provider": result["provider"],
            "dry_run": result.get("dry_run", True),
            "execution_allowed": result.get("execution_allowed", False),
        },
    )
    result["job_id"] = job_id
    return result


__all__ = [
    "image_catalog",
    "image_generate",
    "video_catalog",
    "video_generate",
    "router",
]
