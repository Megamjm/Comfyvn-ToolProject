from __future__ import annotations

from typing import Any, Dict, Mapping

from fastapi import APIRouter, Body, HTTPException

from comfyvn.emulation import engine
from comfyvn.models.adapters import AdapterError

router = APIRouter(prefix="/api/emulation", tags=["Emulation"])


def _ensure_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    raise HTTPException(status_code=400, detail="payload must be a JSON object")


@router.get("/status", summary="Character emulation status snapshot")
def emulation_status() -> Dict[str, Any]:
    return engine.snapshot()


@router.post(
    "/toggle",
    summary="Enable or disable the SillyCompatOffload emulation engine.",
)
def emulation_toggle(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_payload(payload)
    enabled = bool(data.get("enabled"))
    engine.set_enabled(enabled)
    return engine.snapshot()


@router.post(
    "/persona",
    summary="Configure persona memory, style guides, and safety metadata.",
)
def emulation_configure_persona(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_payload(payload)
    persona_id = str(data.get("persona_id") or "").strip()
    if not persona_id:
        raise HTTPException(status_code=400, detail="persona_id is required")
    memory = data.get("memory")
    style_guides = data.get("style_guides")
    safety = data.get("safety")
    metadata = data.get("metadata")
    state = engine.configure_persona(
        persona_id,
        memory=memory if isinstance(memory, list) else None,
        style_guides=style_guides if isinstance(style_guides, list) else None,
        safety=safety if isinstance(safety, Mapping) else None,
        metadata=metadata if isinstance(metadata, Mapping) else None,
    )
    return state.snapshot()


@router.post(
    "/chat",
    summary="Proxy chat requests through the emulation engine (feature-flagged).",
)
def emulation_chat(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_payload(payload)
    persona_id = str(data.get("persona_id") or "").strip() or "default"
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list")

    module = data.get("module")
    provider = data.get("provider") or data.get("provider_id")
    model = data.get("model") or data.get("model_id")
    options = data.get("options")

    try:
        provider_cfg, model_entry, resolved_options = engine.plan_dispatch(
            module=str(module).strip() if module else None,
            provider=str(provider).strip() if provider else None,
            model=str(model).strip() if model else None,
        )
        effective_options = dict(resolved_options)
        if isinstance(options, Mapping):
            effective_options.update(
                {k: v for k, v in options.items() if v is not None}
            )
        result = engine.chat(
            persona_id,
            messages,
            module=str(module).strip() if module else None,
            provider=str(provider).strip() if provider else None,
            model=str(model).strip() if model else None,
            options=effective_options,
        )
    except AdapterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "reply": result.reply,
        "usage": result.usage,
        "metadata": {
            "persona_id": persona_id,
            "module": module,
            "provider": provider_cfg.name,
            "model": model_entry.id,
            "options": effective_options,
        },
        "raw": result.raw,
        "headers": result.headers,
        "status": result.status,
    }
