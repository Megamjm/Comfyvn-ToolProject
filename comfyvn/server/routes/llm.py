from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping

from fastapi import APIRouter, HTTPException

from comfyvn.config import feature_flags
from comfyvn.core.content_filter import content_filter
from comfyvn.models import (
    refresh_registry,
    register_runtime_adapter,
    resolve_provider,
    runtime_registry,
)
from comfyvn.models.adapters import AdapterError, adapter_from_config
from comfyvn.models.registry import iter_models
from comfyvn.rating import rating_service

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _ensure_mapping(payload: Any, *, detail: str) -> MutableMapping[str, Any]:
    if isinstance(payload, MutableMapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


@router.get("/registry")
async def llm_registry() -> Mapping[str, Any]:
    providers: list[dict[str, Any]] = []
    for provider, model in iter_models():
        record = next(
            (item for item in providers if item["name"] == provider.name), None
        )
        model_payload = {
            "id": model.id,
            "label": model.label,
            "tags": list(model.tags),
            "options": dict(model.options),
        }
        if record:
            record.setdefault("models", []).append(model_payload)
            continue
        providers.append(
            {
                "name": provider.name,
                "adapter": provider.adapter,
                "base_url": provider.base_url,
                "timeout": provider.timeout,
                "metadata": dict(provider.metadata),
                "models": [model_payload],
            }
        )
    return {
        "providers": providers,
        "runtime": runtime_registry.snapshot(),
    }


@router.post("/refresh")
async def llm_refresh() -> Mapping[str, Any]:
    refresh_registry()
    return {"ok": True}


@router.get("/runtime")
async def llm_runtime_list() -> Mapping[str, Any]:
    return {"adapters": runtime_registry.snapshot()}


@router.post("/runtime/register")
async def llm_runtime_register(payload: Any) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    adapter_id = str(data.get("id") or data.get("adapter_id") or "").strip()
    provider = str(data.get("provider") or "").strip()
    if not adapter_id:
        raise HTTPException(status_code=400, detail="id is required")
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    modes = []
    raw_modes = data.get("modes")
    if isinstance(raw_modes, (list, tuple)):
        modes = [str(item) for item in raw_modes if str(item).strip()]
    metadata = data.get("metadata")
    if metadata and not isinstance(metadata, Mapping):
        raise HTTPException(status_code=400, detail="metadata must be an object")
    entry = register_runtime_adapter(
        adapter_id,
        provider,
        label=str(data.get("label") or adapter_id),
        modes=modes,
        metadata=dict(metadata or {}),
    )
    return {"adapter": entry.to_dict()}


@router.delete("/runtime/{adapter_id}")
async def llm_runtime_delete(adapter_id: str) -> Mapping[str, Any]:
    runtime_registry.remove(adapter_id)
    return {"ok": True}


@router.post("/test-call")
async def llm_test_call(payload: Any) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    registry_id = str(data.get("registry_id") or data.get("provider") or "").strip()
    if not registry_id:
        raise HTTPException(status_code=400, detail="registry_id is required")

    prompt = str(data.get("prompt") or "").strip()
    messages = data.get("messages")
    if isinstance(messages, list) and messages:
        normalized = [dict(msg) for msg in messages if isinstance(msg, Mapping)]
    else:
        normalized = [{"role": "user", "content": prompt or "Hello from ComfyVN."}]

    rating_gate: Mapping[str, Any] | None = None
    if feature_flags.is_enabled("enable_rating_api"):
        try:
            rating_gate = rating_service().evaluate(
                f"prompt:{registry_id}",
                {
                    "text": prompt or normalized[-1].get("content"),
                    "meta": {"registry": registry_id},
                    "tags": data.get("tags"),
                    "messages": normalized,
                },
                mode=content_filter.mode(),
                acknowledged=bool(data.get("acknowledged")),
                action="llm.test-call",
                ack_token=(str(data.get("ack_token")) or None),
            )
        except Exception:
            LOGGER.warning(
                "Rating evaluation failed for prompt %s", registry_id, exc_info=True
            )
            rating_gate = {
                "ok": False,
                "allowed": True,
                "error": "rating evaluation failed",
            }
        if rating_gate and not rating_gate.get("allowed", True):
            LOGGER.warning(
                "Rating gate blocked llm prompt registry=%s rating=%s ack=%s",
                registry_id,
                (rating_gate.get("rating") or {}).get("rating"),
                rating_gate.get("ack_status"),
            )
            raise HTTPException(
                status_code=423,
                detail={
                    "message": "rating gate blocked prompt",
                    "gate": rating_gate,
                },
            )

    provider = resolve_provider(registry_id)
    if not provider:
        runtime_entry = runtime_registry.get(registry_id)
        if not runtime_entry:
            raise HTTPException(
                status_code=404, detail=f"adapter '{registry_id}' not found"
            )
        reply = f"(runtime:{runtime_entry.adapter_id}) {normalized[-1]['content']}"
        return {
            "ok": True,
            "runtime": runtime_entry.to_dict(),
            "data": {"reply": reply},
            "rating_gate": rating_gate,
        }

    model = str(data.get("model") or "").strip()
    if not model:
        if provider.models:
            model = provider.models[0].id
        else:
            raise HTTPException(
                status_code=400, detail="model is required for this provider"
            )

    adapter = adapter_from_config(provider)
    try:
        result = adapter.chat(model, normalized)
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.debug("LLM test call failed: %s", exc)
        raise HTTPException(status_code=500, detail="adapter execution failed") from exc

    return {
        "ok": True,
        "data": {
            "reply": result.reply,
            "raw": result.raw,
            "headers": result.headers,
            "usage": result.usage,
        },
        "rating_gate": rating_gate,
    }
