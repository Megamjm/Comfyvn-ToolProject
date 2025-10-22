from __future__ import annotations

"""
RunPod public adapter.

Exposes metadata, health, and dry-run submit/poll helpers so Studio tooling can
exercise workflows without live API traffic.  Real executions remain opt-in
behind feature flags and credentials.
"""

from typing import Any, Dict, Mapping

from . import provider_secrets, resolve_credential

PROVIDER_ID = "runpod"
DISPLAY_NAME = "RunPod"
FEATURE_FLAG = "enable_public_gpu"
PRICING_URL = "https://www.runpod.io/pricing"
DOCS_URL = "https://docs.runpod.io/docs"
LAST_CHECKED = "2025-02-17"
ENV_KEYS: tuple[str, ...] = ("RUNPOD_API_KEY", "RUNPOD_TOKEN")
SECRET_KEYS: tuple[str, ...] = ("token", "api_key")
ALIASES: tuple[str, ...] = ("runpod", "runpod.io")
CAPABILITIES: Dict[str, Any] = {
    "supports": ["serverless", "pods", "volumes", "websocket_streaming"],
    "gpu_families": ["RTX_4090", "RTX_6000_ADA", "A100_80GB"],
    "regions": ["us-texas", "eu-finland", "ap-sydney"],
}


def metadata() -> Dict[str, Any]:
    return {
        "id": PROVIDER_ID,
        "name": DISPLAY_NAME,
        "pricing_url": PRICING_URL,
        "docs_url": DOCS_URL,
        "last_checked": LAST_CHECKED,
        "capabilities": CAPABILITIES,
        "feature_flag": FEATURE_FLAG,
        "env_keys": list(ENV_KEYS),
        "aliases": list(ALIASES),
    }


def _token_from(config: Mapping[str, object]) -> str:
    token = resolve_credential(
        PROVIDER_ID,
        env_keys=ENV_KEYS,
        secret_keys=SECRET_KEYS,
    )
    if token:
        return token.strip()
    raw = config.get("token") or config.get("api_key")
    return str(raw or "").strip()


def _config_with_defaults(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    payload: Dict[str, object] = {}
    payload.update(provider_secrets(PROVIDER_ID))
    if cfg:
        payload.update(dict(cfg))
    return payload


def _with_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    base = metadata()
    enriched = dict(payload)
    enriched.setdefault("provider", base["id"])
    enriched.setdefault("pricing_url", base["pricing_url"])
    enriched.setdefault("docs_url", base["docs_url"])
    enriched.setdefault("last_checked", base["last_checked"])
    enriched.setdefault("capabilities", base["capabilities"])
    enriched.setdefault("dry_run", True)
    return enriched


def health(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    """
    Validate RunPod credentials and expose dry-run metadata.
    """

    config = _config_with_defaults(cfg)
    token = _token_from(config)
    if not token:
        return _with_metadata(
            {"ok": False, "reason": "missing token or api_key", "dry_run": True}
        )
    return _with_metadata({"ok": True, "credential": "present"})


def submit(
    job: Mapping[str, object], cfg: Mapping[str, object] | None = None
) -> Dict[str, object]:
    """
    Submit a job sketch to RunPod.  Returns deterministic identifiers for dry-run flows.
    """

    config = _config_with_defaults(cfg)
    token = _token_from(config)
    payload = {
        "job": dict(job),
        "id": "mock-runpod-1",
        "note": "dry-run",
        "dry_run": True,
    }
    if not token:
        payload.update({"ok": False, "reason": "missing token or api_key"})
        return _with_metadata(payload)
    payload.update({"ok": True})
    return _with_metadata(payload)


def poll(job_id: str, cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    """
    Poll the status of a previously submitted job.  Dry-run results always complete successfully.
    """

    _config_with_defaults(cfg)  # ensures consistent merge / placeholder
    return _with_metadata(
        {
            "ok": True,
            "status": "done",
            "job_id": job_id or "mock-runpod-1",
            "artifacts": [],
        }
    )


__all__ = [
    "ALIASES",
    "CAPABILITIES",
    "DOCS_URL",
    "FEATURE_FLAG",
    "ENV_KEYS",
    "LAST_CHECKED",
    "PRICING_URL",
    "health",
    "metadata",
    "poll",
    "submit",
]
