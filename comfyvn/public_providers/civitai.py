from __future__ import annotations

"""
Civitai public catalog adapter (Phase-7).

Provides read-only helpers for health, search, metadata, and download planning.
Real downloads remain gated behind the Phase-7 license enforcer; this module
only returns normalized payloads that downstream tooling can inspect without
pulling binaries.
"""

import logging
import os
import time
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import httpx

from . import provider_secrets, resolve_credential

LOGGER = logging.getLogger(__name__)

PROVIDER_ID = "civitai"
FEATURE_FLAG = "enable_public_model_hubs"
API_BASE = "https://civitai.com/api/v1"
DOCS_URL = "https://github.com/civitai/civitai/wiki/API-Reference"
PRICING_URL = "https://civitai.com/pricing"
TERMS_URL = "https://civitai.com/terms-of-service"
LAST_CHECKED = "2025-02-20"
RATE_LIMIT_NOTES = "Public REST endpoints allow ~60 requests/minute per IP; API tokens can raise quotas."
TIMEOUT = httpx.Timeout(6.0)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
ENV_KEYS: tuple[str, ...] = ("COMFYVN_CIVITAI_TOKEN", "CIVITAI_API_TOKEN")
SECRET_KEYS: tuple[str, ...] = ("api_key", "token", "key")


class CivitaiError(RuntimeError):
    """Raised when the upstream API returns an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _auth_token(config: Optional[Mapping[str, Any]] = None) -> str:
    token = resolve_credential(
        PROVIDER_ID,
        env_keys=ENV_KEYS,
        secret_keys=SECRET_KEYS,
    )
    if token:
        return token.strip()
    if config:
        raw = config.get("api_key") or config.get("token")
        if isinstance(raw, str):
            return raw.strip()
    return ""


def _credential_snapshot(config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    secrets = provider_secrets(PROVIDER_ID)
    env_hits = {key: bool(os.getenv(key)) for key in ENV_KEYS}
    secret_hits = {key: bool(secrets.get(key)) for key in SECRET_KEYS}
    token = _auth_token(config)
    return {
        "env": env_hits,
        "secrets": secret_hits,
        "token_present": bool(token),
    }


def _headers(token: str) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "User-Agent": "ComfyVN-Civitai/0.1 (+https://comfyvn.dev)",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-API-Key"] = token
    return headers


def _request(
    path: str, *, params: Optional[Mapping[str, Any]] = None, token: str = ""
) -> Dict[str, Any]:
    url = f"{API_BASE}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(url, params=params, headers=_headers(token))
    except httpx.TimeoutException as exc:
        raise CivitaiError(f"timeout contacting {url}") from exc
    except httpx.HTTPError as exc:
        raise CivitaiError(f"request failed for {url}: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise CivitaiError(
            f"Civitai responded with {response.status_code}: {detail}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise CivitaiError("invalid JSON payload from Civitai") from exc
    return payload


def credentials_present() -> bool:
    return bool(_auth_token())


def _license_block(payload: Mapping[str, Any]) -> Dict[str, Any]:
    commercial = payload.get("allowCommercialUse")
    if isinstance(commercial, Iterable) and not isinstance(commercial, (str, bytes)):
        commercial = [str(item) for item in commercial]
    elif commercial is not None:
        commercial = bool(commercial)

    return {
        "credit_required": not bool(payload.get("allowNoCredit", False)),
        "allow_commercial_use": commercial,
        "allow_derivatives": bool(payload.get("allowDerivatives", False)),
        "allow_relicense": bool(payload.get("allowDifferentLicense", False)),
    }


def _primary_file(files: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not files:
        return None
    for entry in files:
        if entry.get("primary"):
            return entry
    return files[0]


def _file_summary(entry: Mapping[str, Any]) -> Dict[str, Any]:
    size_kb = float(entry.get("sizeKB") or 0.0)
    metadata = entry.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "format": metadata.get("format"),
        "precision": metadata.get("fp"),
        "size_mb": round(size_kb / 1024.0, 2) if size_kb else None,
        "download_url": entry.get("downloadUrl"),
        "primary": bool(entry.get("primary")),
        "sha256": (entry.get("hashes") or {}).get("SHA256"),
        "metadata": metadata,
    }


def _version_summary(version: Mapping[str, Any]) -> Dict[str, Any]:
    files = version.get("files") or []
    if not isinstance(files, Sequence):
        files = []
    file_summaries = [
        _file_summary(file_entry)
        for file_entry in files
        if isinstance(file_entry, Mapping)
    ]
    primary = _primary_file(files)
    size_mb = None
    if primary:
        primary_size = primary.get("sizeKB")
        try:
            size_mb = round(float(primary_size) / 1024.0, 2)
        except Exception:
            size_mb = None
    return {
        "id": version.get("id"),
        "name": version.get("name"),
        "published_at": version.get("publishedAt"),
        "nsfw_level": version.get("nsfwLevel"),
        "base_model": version.get("baseModel"),
        "base_model_type": version.get("baseModelType"),
        "trained_words": version.get("trainedWords") or [],
        "download_url": version.get("downloadUrl"),
        "files": file_summaries,
        "primary_file": (
            _file_summary(primary) if isinstance(primary, Mapping) else None
        ),
        "size_mb": size_mb,
        "stats": version.get("stats") or {},
        "supports_generation": bool(version.get("supportsGeneration")),
    }


def _normalize_model(
    payload: Mapping[str, Any], *, include_versions: bool
) -> Dict[str, Any]:
    versions = payload.get("modelVersions") or []
    if not isinstance(versions, Sequence):
        versions = []
    normalized_versions = [
        _version_summary(version)
        for version in versions
        if isinstance(version, Mapping)
    ]
    primary_version = normalized_versions[0] if normalized_versions else None

    metadata = {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "type": payload.get("type"),
        "model_type": (payload.get("type") or "").title(),
        "nsfw": bool(payload.get("nsfw")),
        "nsfw_level": payload.get("nsfwLevel"),
        "availability": payload.get("availability"),
        "stats": payload.get("stats") or {},
        "tags": payload.get("tags") or [],
        "license": _license_block(payload),
        "creator": payload.get("creator") or {},
    }
    if include_versions:
        metadata["versions"] = normalized_versions
    else:
        metadata["version"] = primary_version
    return metadata


def health(config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    snapshot = _credential_snapshot(config)
    token = _auth_token(config)
    started = time.perf_counter()
    try:
        data = _request("/models", params={"limit": 1}, token=token)
        latency_ms = round((time.perf_counter() - started) * 1000.0)
        ok = True
        sample = data.get("items") or []
        if isinstance(sample, Sequence) and sample:
            sample = _normalize_model(sample[0], include_versions=False)
        else:
            sample = None
        return {
            "provider": PROVIDER_ID,
            "ok": ok,
            "dry_run": True,
            "latency_ms": latency_ms,
            "pricing_url": PRICING_URL,
            "docs_url": DOCS_URL,
            "terms_url": TERMS_URL,
            "last_checked": LAST_CHECKED,
            "rate_limit_notes": RATE_LIMIT_NOTES,
            "credentials": snapshot,
            "sample": sample,
        }
    except CivitaiError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000.0)
        LOGGER.warning("Civitai health probe failed: %s", exc)
        return {
            "provider": PROVIDER_ID,
            "ok": False,
            "dry_run": True,
            "latency_ms": latency_ms,
            "pricing_url": PRICING_URL,
            "docs_url": DOCS_URL,
            "terms_url": TERMS_URL,
            "last_checked": LAST_CHECKED,
            "rate_limit_notes": RATE_LIMIT_NOTES,
            "error": str(exc),
            "status_code": getattr(exc, "status_code", None),
            "credentials": snapshot,
        }


def search_models(
    *,
    query: str,
    limit: int = DEFAULT_LIMIT,
    model_types: Sequence[str] | None = None,
    allow_nsfw: bool = False,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if not query.strip():
        raise ValueError("query is required")
    token = _auth_token(config)
    params: Dict[str, Any] = {
        "query": query.strip(),
        "limit": max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT)),
    }
    if model_types:
        params["types"] = ",".join(sorted({str(item) for item in model_types}))
    if allow_nsfw:
        params["nsfw"] = "true"
    else:
        params["nsfw"] = "false"
    data = _request("/models", params=params, token=token)
    items = data.get("items") or []
    if not isinstance(items, Sequence):
        items = []
    normalized = [
        _normalize_model(item, include_versions=False)
        for item in items
        if isinstance(item, Mapping)
    ]
    return {
        "provider": PROVIDER_ID,
        "query": query.strip(),
        "limit": params["limit"],
        "count": len(normalized),
        "items": normalized,
        "allow_nsfw": allow_nsfw,
        "model_types": params.get("types"),
        "dry_run": True,
        "pricing_url": PRICING_URL,
        "docs_url": DOCS_URL,
        "last_checked": LAST_CHECKED,
        "rate_limit_notes": RATE_LIMIT_NOTES,
    }


def fetch_metadata(
    model_id: int,
    *,
    version_id: Optional[int] = None,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    token = _auth_token(config)
    data = _request(f"/models/{model_id}", token=token)
    normalized = _normalize_model(data, include_versions=True)
    versions = normalized.get("versions") or []
    selected = None
    if version_id is not None:
        for version in versions:
            if version.get("id") == version_id:
                selected = version
                break
    if selected is None and versions:
        selected = versions[0]
    normalized["selected_version"] = selected
    normalized["dry_run"] = True
    normalized["pricing_url"] = PRICING_URL
    normalized["docs_url"] = DOCS_URL
    normalized["terms_url"] = TERMS_URL
    normalized["last_checked"] = LAST_CHECKED
    normalized["rate_limit_notes"] = RATE_LIMIT_NOTES
    return normalized


def plan_download(
    model_id: int,
    *,
    version_id: Optional[int] = None,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    metadata = fetch_metadata(model_id, version_id=version_id, config=config)
    selected = metadata.get("selected_version") or {}
    files = selected.get("files") or []
    size_total = 0.0
    for file_entry in files:
        size = file_entry.get("size_mb")
        if isinstance(size, (int, float)):
            size_total += float(size)
    token_present = bool(_auth_token(config))
    plan = {
        "provider": PROVIDER_ID,
        "model_id": model_id,
        "version_id": selected.get("id"),
        "version_name": selected.get("name"),
        "download_url": selected.get("download_url"),
        "total_size_mb": round(size_total, 2) if size_total else None,
        "files": files,
        "license": metadata.get("license"),
        "nsfw": metadata.get("nsfw"),
        "nsfw_level": metadata.get("nsfw_level"),
        "terms_url": TERMS_URL,
        "pricing_url": PRICING_URL,
        "docs_url": DOCS_URL,
        "last_checked": LAST_CHECKED,
        "rate_limit_notes": RATE_LIMIT_NOTES,
        "dry_run": True,
        "auth": {
            "token_present": token_present,
        },
    }
    return plan


__all__ = [
    "CivitaiError",
    "FEATURE_FLAG",
    "TERMS_URL",
    "DOCS_URL",
    "PRICING_URL",
    "LAST_CHECKED",
    "RATE_LIMIT_NOTES",
    "credentials_present",
    "fetch_metadata",
    "health",
    "plan_download",
    "search_models",
]
