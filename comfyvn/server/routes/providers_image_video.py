from __future__ import annotations

"""
Public image/video provider routes.

These endpoints surface catalog metadata and accept dry-run generation payloads.
Actual network execution remains opt-in behind feature flags and credentials.
"""

import logging
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

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


def _metadata(module: object) -> Dict[str, Any]:
    meta_fn = getattr(module, "metadata", None)
    if callable(meta_fn):
        try:
            meta = dict(meta_fn())  # type: ignore[call-arg]
            return meta
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Metadata lookup failed for %s: %s", module, exc)
    try:
        entry = dict(module.catalog_entry())
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Catalog fallback failed for %s: %s", module, exc)
        entry = {}
    return {
        "id": entry.get("id") or getattr(module, "PROVIDER_ID", ""),
        "name": entry.get("label") or entry.get("name"),
        "pricing_url": entry.get("pricing_url"),
        "docs_url": entry.get("docs_url"),
        "last_checked": entry.get("last_checked"),
        "capabilities": entry.get("capabilities"),
    }


def _flag_enabled(flag_name: str, *, kind: str) -> bool:
    if feature_flags.is_enabled(flag_name):
        return True
    if kind in {"image", "video"} and flag_name != "enable_public_image_video":
        return feature_flags.is_enabled("enable_public_image_video")
    return False


def _feature_context(module: object, *, kind: str) -> Dict[str, Any]:
    flag = _flag_name(
        module,
        (
            "enable_public_image_video"
            if kind == "image"
            else "enable_public_video_providers"
        ),
    )
    enabled = _flag_enabled(flag, kind=kind)
    return {"feature": flag, "enabled": enabled}


def _enrich_result(
    module: object, kind: str, payload: Mapping[str, Any]
) -> Dict[str, Any]:
    meta = _metadata(module)
    result = dict(payload)
    result.setdefault("provider", meta.get("id"))
    result.setdefault("kind", kind)
    result.setdefault("pricing_url", meta.get("pricing_url"))
    result.setdefault("docs_url", meta.get("docs_url"))
    result.setdefault("last_checked", meta.get("last_checked"))
    result.setdefault("capabilities", meta.get("capabilities"))
    result.setdefault("dry_run", True)

    feature = _feature_context(module, kind=kind)
    result["feature"] = feature
    if not feature["enabled"]:
        result.setdefault("ok", False)
        result.setdefault("reason", "feature disabled")
    return result


def _extract_config(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    cfg = payload.get("config") or payload.get("cfg") or {}
    if isinstance(cfg, Mapping):
        return dict(cfg)
    return {}


def _prepare_request_payload(data: Mapping[str, Any]) -> Dict[str, Any]:
    request = dict(data)
    for key in ("provider", "provider_id", "config", "cfg"):
        request.pop(key, None)
    return request


def _invoke_submit(
    module: object,
    request: Mapping[str, Any],
    *,
    execute: bool,
    config: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    submit_fn = getattr(module, "submit", None)
    if callable(submit_fn):
        try:
            return submit_fn(request, execute=execute, config=config)
        except TypeError:
            return submit_fn(request, execute=execute)
    generate_fn = getattr(module, "generate")
    try:
        return generate_fn(request, execute=execute, config=config)
    except TypeError:
        return generate_fn(request, execute=execute)


def _invoke_poll(
    module: object,
    job_id: str,
    config: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    poll_fn = getattr(module, "poll", None)
    if callable(poll_fn):
        try:
            return poll_fn(job_id, config)
        except TypeError:
            return poll_fn(job_id)
    return {"ok": True, "status": "done", "job_id": job_id, "dry_run": True}


def _invoke_health(
    module: object,
    config: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    health_fn = getattr(module, "health", None)
    if callable(health_fn):
        try:
            return health_fn(config)
        except TypeError:
            return health_fn()
    try:
        credentials = bool(module.credentials_present())
    except Exception:  # pragma: no cover - defensive
        credentials = False
    return {"ok": credentials, "dry_run": True}


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
        meta = _metadata(module)
        entry.setdefault("pricing_url", meta.get("pricing_url"))
        entry.setdefault("docs_url", meta.get("docs_url"))
        entry.setdefault("capabilities", meta.get("capabilities"))
        entry.setdefault("last_checked", meta.get("last_checked"))
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


@router.post("/image/{provider_id}/health")
async def image_health(
    provider_id: str,
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    module = _resolve_module("image", provider_id)
    cfg = _extract_config(payload if isinstance(payload, Mapping) else None)
    status = _invoke_health(module, cfg)
    return _enrich_result(module, "image", status)


@router.post("/video/{provider_id}/health")
async def video_health(
    provider_id: str,
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    module = _resolve_module("video", provider_id)
    cfg = _extract_config(payload if isinstance(payload, Mapping) else None)
    status = _invoke_health(module, cfg)
    return _enrich_result(module, "video", status)


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
    config = _extract_config(payload)
    request_payload = _prepare_request_payload(payload)
    try:
        raw = _invoke_submit(
            module,
            request_payload,
            execute=allow_execute,
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("public %s provider failed: %s", kind, exc)
        raise HTTPException(
            status_code=500, detail="provider execution failed"
        ) from exc

    result = _enrich_result(module, kind, raw)
    if "execution_allowed" not in result:
        result["execution_allowed"] = allow_execute
    if "ok" not in result:
        result["ok"] = bool(result.get("execution_allowed"))
    return result


@router.post("/image/{provider_id}/submit")
async def image_submit(
    provider_id: str,
    payload: Any = Body(...),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    module = _resolve_module("image", provider_id)
    result = _generate("image", module, data)
    job_id = _register_job("image", result["provider"], result)
    LOGGER.info(
        "public.image.submit",
        extra={
            "provider": result["provider"],
            "dry_run": result.get("dry_run", True),
            "execution_allowed": result.get("execution_allowed", False),
        },
    )
    result["job_id"] = job_id
    return result


@router.post("/video/{provider_id}/submit")
async def video_submit(
    provider_id: str,
    payload: Any = Body(...),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    module = _resolve_module("video", provider_id)
    result = _generate("video", module, data)
    job_id = _register_job("video", result["provider"], result)
    LOGGER.info(
        "public.video.submit",
        extra={
            "provider": result["provider"],
            "dry_run": result.get("dry_run", True),
            "execution_allowed": result.get("execution_allowed", False),
        },
    )
    result["job_id"] = job_id
    return result


@router.post("/image/{provider_id}/poll")
async def image_poll(
    provider_id: str,
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    module = _resolve_module("image", provider_id)
    cfg = _extract_config(data)
    job_id = str(data.get("job_id") or data.get("id") or "").strip()
    status = _invoke_poll(module, job_id or f"mock-{provider_id}-1", cfg)
    return _enrich_result(module, "image", status)


@router.post("/video/{provider_id}/poll")
async def video_poll(
    provider_id: str,
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    module = _resolve_module("video", provider_id)
    cfg = _extract_config(data)
    job_id = str(data.get("job_id") or data.get("id") or "").strip()
    status = _invoke_poll(module, job_id or f"mock-{provider_id}-1", cfg)
    return _enrich_result(module, "video", status)


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
    "image_health",
    "image_generate",
    "image_poll",
    "image_submit",
    "video_catalog",
    "video_health",
    "video_generate",
    "video_poll",
    "video_submit",
    "router",
]
