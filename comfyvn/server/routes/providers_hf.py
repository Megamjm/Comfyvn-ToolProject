from __future__ import annotations

"""
FastAPI routes exposing the Hugging Face Hub public connector.
"""

from typing import Any, Dict, Iterable, Mapping, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.config import feature_flags
from comfyvn.public_providers import hf_hub, resolve_credential

router = APIRouter(prefix="/api/providers/hf", tags=["Hugging Face Hub"])


def _feature_context() -> Dict[str, Any]:
    enabled = feature_flags.is_enabled(hf_hub.FEATURE_FLAG)
    return {"feature": hf_hub.FEATURE_FLAG, "enabled": enabled}


def _with_feature(payload: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(payload)
    feature = _feature_context()
    data["feature"] = feature
    if not feature["enabled"]:
        data.setdefault("ok", False)
        data.setdefault("reason", "feature disabled")
    return data


def _coerce_kind(kind: Optional[str]) -> str:
    if not kind:
        return hf_hub.DEFAULT_KIND
    value = str(kind).strip().lower()
    if value not in {"model", "dataset", "space"}:
        raise HTTPException(
            status_code=400, detail="invalid kind; expected model, dataset, or space"
        )
    return value


def _token_from_sources(
    explicit: Optional[str] = None,
    *,
    config: Mapping[str, Any] | None = None,
    auto: bool = False,
) -> Optional[str]:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    if config:
        for key in (
            "token",
            "api_token",
            "hf_token",
            "huggingface_token",
            "hf_api_token",
        ):
            raw = config.get(key)
            if raw:
                return str(raw).strip()
    if auto:
        resolved = resolve_credential(
            hf_hub.PROVIDER_ID,
            env_keys=hf_hub.ENV_KEYS,
            secret_keys=hf_hub.SECRET_KEYS,
        )
        if resolved:
            return resolved.strip()
    return None


@router.get(
    "/health",
    summary="Basic connector health (metadata only)",
)
async def hf_health() -> Dict[str, Any]:
    return _with_feature(hf_hub.health())


@router.get(
    "/search",
    summary="Search Hugging Face Hub repositories",
)
async def hf_search(
    q: str = Query(..., alias="query", min_length=1),
    kind: Optional[str] = Query(
        hf_hub.DEFAULT_KIND,
        description="Repository kind: model, dataset, or space.",
    ),
    limit: int = Query(
        hf_hub.SEARCH_LIMIT_DEFAULT,
        ge=1,
        le=hf_hub.SEARCH_LIMIT_MAX,
        description="Result limit (caps at 50).",
    ),
    use_token: bool = Query(
        False,
        alias="auth",
        description="When true, attempt to use stored hf_token for gated/private repos.",
    ),
    token: Optional[str] = Query(
        None,
        description="Optional explicit Hugging Face token (overrides stored secrets).",
    ),
) -> Dict[str, Any]:
    resolved_kind = _coerce_kind(kind)
    resolved_token = _token_from_sources(token, auto=use_token)
    try:
        result = hf_hub.search(
            q,
            kind=resolved_kind,
            limit=limit,
            token=resolved_token,
        )
    except hf_hub.ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or str(exc))
    return _with_feature(result)


@router.get(
    "/metadata",
    summary="Inspect repository metadata and files",
)
async def hf_metadata(
    repo_id: str = Query(..., alias="id", min_length=1),
    kind: Optional[str] = Query(
        hf_hub.DEFAULT_KIND,
        description="Repository kind: model, dataset, or space.",
    ),
    revision: Optional[str] = Query(
        None,
        description="Optional git revision (branch, tag, or commit).",
    ),
    use_token: bool = Query(
        False,
        alias="auth",
        description="When true, attempt to use stored hf_token for gated/private repos.",
    ),
    token: Optional[str] = Query(
        None,
        description="Optional explicit Hugging Face token (overrides stored secrets).",
    ),
) -> Dict[str, Any]:
    resolved_kind = _coerce_kind(kind)
    resolved_token = _token_from_sources(token, auto=use_token)
    try:
        result = hf_hub.model_metadata(
            repo_id,
            kind=resolved_kind,
            revision=revision,
            token=resolved_token,
        )
    except hf_hub.ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or str(exc))
    return _with_feature(result)


def _ensure_mapping(payload: Any, *, detail: str) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


def _list_from(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[list[str]]:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            items = [part.strip() for part in value.split(",") if part.strip()]
            if items:
                return items
    return None


@router.post(
    "/pull",
    summary="Plan a token-gated repository pull (dry-run only)",
)
async def hf_pull(
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    repo_id = str(
        data.get("repo_id")
        or data.get("repo")
        or data.get("id")
        or data.get("model_id")
        or "",
    ).strip()
    if not repo_id:
        raise HTTPException(status_code=400, detail="repository id required")
    kind = _coerce_kind(str(data.get("kind") or hf_hub.DEFAULT_KIND))
    revision = str(data.get("revision") or data.get("ref") or "").strip() or None
    ack = bool(
        data.get("ack_license")
        or data.get("acknowledge_license")
        or data.get("license_ack")
    )
    files = _list_from(data, ("files", "paths", "artifacts"))
    config = data.get("config")
    config_mapping: Mapping[str, Any] | None
    if isinstance(config, Mapping):
        config_mapping = config
    else:
        config_mapping = data
    explicit_token = _token_from_sources(
        data.get("token"),
        config=config_mapping,
        auto=False,
    )
    if explicit_token:
        merged_config = dict(config_mapping or {})
        merged_config["token"] = explicit_token
        config_mapping = merged_config
    try:
        result = hf_hub.prepare_pull(
            repo_id,
            kind=kind,
            revision=revision,
            files=files,
            config=config_mapping,
            ack_license=ack,
        )
    except hf_hub.ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload or str(exc))
    return _with_feature(result)


__all__ = ["router"]
