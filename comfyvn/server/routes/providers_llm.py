from __future__ import annotations

"""
Public LLM provider registry and dry-run chat router.
"""

from typing import Any, Dict, Iterable, Mapping, Sequence

from fastapi import APIRouter, Body

from comfyvn.config import feature_flags
from comfyvn.public_providers import (
    catalog,
    llm_anthropic,
    llm_gemini,
    llm_openai,
    llm_openrouter,
)

router = APIRouter(prefix="/api/providers/llm", tags=["LLM Providers (public)"])

FEATURE_FLAG = "enable_public_llm"


def _feature_context() -> Dict[str, Any]:
    enabled = feature_flags.is_enabled(FEATURE_FLAG)
    return {"feature": FEATURE_FLAG, "enabled": enabled}


def _merge_entry(module: Any) -> Dict[str, Any]:
    entry = module.registry_entry()
    health = module.health()
    models = entry.get("models", [])
    merged = dict(entry)
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
    merged["models"] = models
    return merged


def _providers() -> Sequence[Any]:
    return (llm_openai, llm_anthropic, llm_gemini, llm_openrouter)


def _registry() -> Dict[str, Any]:
    providers = [_merge_entry(provider) for provider in _providers()]
    tags: set[str] = set()
    models: list[Dict[str, Any]] = []
    for entry in providers:
        for model in entry.get("models", []):
            models.append(
                {
                    "id": model.get("id"),
                    "provider": entry.get("id"),
                    "label": model.get("label"),
                    "tags": model.get("tags", []),
                    "pricing": model.get("pricing", {}),
                    "context": model.get("context"),
                }
            )
            tags.update(tag for tag in model.get("tags", []) if isinstance(tag, str))
    return {
        "providers": providers,
        "models": models,
        "tags": sorted(tags),
    }


@router.get("/registry", summary="LLM provider registry")
async def llm_registry() -> Dict[str, Any]:
    feature = _feature_context()
    reg = _registry()
    prices = {
        "openai": llm_openai.registry_entry().get("pricing_url"),
        "anthropic": llm_anthropic.registry_entry().get("pricing_url"),
        "google_gemini": llm_gemini.registry_entry().get("pricing_url"),
        "openrouter": llm_openrouter.registry_entry().get("pricing_url"),
    }
    return {
        "ok": feature["enabled"],
        "feature": feature,
        "providers": reg["providers"],
        "models": reg["models"],
        "tags": reg["tags"],
        "pricing_links": prices,
    }


@router.get("/public/catalog", summary="List LLM providers with pricing heuristics")
async def llm_catalog() -> Dict[str, Any]:
    return {
        "ok": True,
        "feature": _feature_context(),
        "providers": catalog.catalog_for("llm_inference"),
    }


def _plan_for_provider(provider_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    provider_map = {
        "openai": llm_openai,
        "anthropic": llm_anthropic,
        "google_gemini": llm_gemini,
        "gemini": llm_gemini,
        "openrouter": llm_openrouter,
    }
    module = provider_map.get(provider_id.lower())
    if not module:
        return {
            "ok": False,
            "dry_run": True,
            "reason": f"provider '{provider_id}' unsupported",
        }
    plan = module.plan_chat(payload)
    plan.setdefault("dry_run", True)
    plan["provider"] = module.registry_entry().get("id")
    plan["pricing_url"] = module.registry_entry().get("pricing_url")
    return {
        "ok": True,
        "dry_run": True,
        "plan": plan,
    }


@router.post("/chat", summary="Dry-run LLM router plan")
async def llm_chat(
    payload: Mapping[str, Any] = Body(default_factory=dict),
) -> Dict[str, Any]:
    provider = str(payload.get("provider") or payload.get("route") or "openai")
    feature = _feature_context()
    result = _plan_for_provider(provider, payload)
    result["feature"] = feature
    result.setdefault("dry_run", True)
    if not feature["enabled"]:
        result["ok"] = False
        result.setdefault("plan", {})
        result["reason"] = "feature disabled"
    return result


__all__ = ["router"]
