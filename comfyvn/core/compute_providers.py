from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

LOGGER = logging.getLogger(__name__)


def _http_get(url: str, headers: Optional[dict] = None, timeout: float = 5.0) -> Any:
    response = httpx.get(url, headers=headers or {}, timeout=timeout)
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


def _http_post(
    url: str, body: dict, headers: Optional[dict] = None, timeout: float = 10.0
) -> Any:
    response = httpx.post(url, json=body, headers=headers or {}, timeout=timeout)
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


def _build_headers(provider: Dict[str, Any]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    cfg = provider.get("config") or {}
    token = cfg.get("api_key") or provider.get("auth")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cfg.get("headers"):
        headers.update(cfg["headers"])
    return headers


def comfyui_health(base_url: str) -> dict:
    try:
        _http_get(base_url.rstrip("/") + "/system_stats")
        return {"ok": True}
    except Exception as exc:  # pragma: no cover - relies on external binary
        LOGGER.debug("ComfyUI health check failed for %s: %s", base_url, exc)
        return {"ok": False, "error": str(exc)}


def comfyui_send(base_url: str, payload: dict) -> dict:
    try:
        result = _http_post(base_url.rstrip("/") + "/prompt", payload)
        return {"ok": True, "result": result}
    except Exception as exc:  # pragma: no cover - network call
        LOGGER.warning("ComfyUI send failed for %s: %s", base_url, exc)
        return {"ok": False, "error": str(exc)}


def generic_health(base_url: str, headers: Optional[dict] = None) -> dict:
    try:
        _http_get(base_url.rstrip("/"), headers=headers)
        return {"ok": True}
    except Exception as exc:  # pragma: no cover - network call
        LOGGER.debug("Generic health check failed for %s: %s", base_url, exc)
        return {"ok": False, "error": str(exc)}


def generic_send(base_url: str, payload: dict, headers: Optional[dict] = None) -> dict:
    try:
        result = _http_post(
            base_url.rstrip("/") + "/jobs/enqueue", payload, headers=headers
        )
        return {"ok": True, "result": result}
    except Exception as exc:  # pragma: no cover - network call
        LOGGER.warning("Generic provider send failed for %s: %s", base_url, exc)
        return {"ok": False, "error": str(exc)}


def _service_type(provider: Dict[str, Any]) -> str:
    return (
        provider.get("service") or provider.get("kind") or provider.get("type") or ""
    ).lower()


def _base_url(provider: Dict[str, Any]) -> str:
    return (
        provider.get("base_url")
        or provider.get("base")
        or provider.get("endpoint")
        or ""
    )


def health(provider: Dict[str, Any]) -> dict:
    """Run a lightweight health check for the provider."""
    base_url = _base_url(provider).strip()
    if not base_url:
        return {"ok": False, "error": "missing base_url"}
    service = _service_type(provider)
    headers = _build_headers(provider)
    if service in {"comfyui", "local"}:
        return comfyui_health(base_url)
    return generic_health(base_url, headers=headers)


def send_job(provider: Dict[str, Any], payload: Dict[str, Any]) -> dict:
    """Send a job payload to the target provider."""
    base_url = _base_url(provider).strip()
    if not base_url:
        return {"ok": False, "error": "missing base_url"}
    service = _service_type(provider)
    headers = _build_headers(provider)
    if service in {"comfyui", "local"}:
        return comfyui_send(base_url, payload)
    return generic_send(base_url, payload, headers=headers)
