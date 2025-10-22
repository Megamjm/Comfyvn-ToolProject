from __future__ import annotations

"""
Replicate API adapter.

Captures catalog metadata and provides dry-run helper flows so Studio tooling
can validate payloads without invoking hosted models.
"""

from typing import Any, Dict, Mapping

from . import provider_secrets, resolve_credential

PROVIDER_ID = "replicate"
DISPLAY_NAME = "Replicate"
FEATURE_FLAG = "enable_public_gpu"
PRICING_URL = "https://replicate.com/pricing"
DOCS_URL = "https://replicate.com/docs"
LAST_CHECKED = "2025-02-17"
ENV_KEYS: tuple[str, ...] = ("REPLICATE_API_TOKEN", "REPLICATE_API_KEY")
SECRET_KEYS: tuple[str, ...] = ("token", "api_key")
ALIASES: tuple[str, ...] = ("replicate", "replicate.com")
CAPABILITIES: Dict[str, Any] = {
    "supports": ["model_marketplace", "async_jobs", "webhooks", "streaming"],
    "gpu_families": ["varies_per_model"],
    "pricing_model": "per-second with model-specific rates",
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
    token = resolve_credential(PROVIDER_ID, env_keys=ENV_KEYS, secret_keys=SECRET_KEYS)
    if token:
        return token.strip()
    raw = config.get("token") or config.get("api_key")
    return str(raw or "").strip()


def _config_with_defaults(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    config: Dict[str, object] = {}
    config.update(provider_secrets(PROVIDER_ID))
    if cfg:
        config.update(dict(cfg))
    return config


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
    config = _config_with_defaults(cfg)
    token = _token_from(config)
    if not token:
        return _with_metadata(
            {"ok": False, "reason": "missing replicate api token", "dry_run": True}
        )
    return _with_metadata({"ok": True, "credential": "present"})


def submit(
    job: Mapping[str, object], cfg: Mapping[str, object] | None = None
) -> Dict[str, object]:
    config = _config_with_defaults(cfg)
    token = _token_from(config)
    model_ref = str(job.get("model") or job.get("model_version") or "owner/model")
    payload = {
        "job": dict(job),
        "model": model_ref,
        "id": "mock-replicate-1",
        "dry_run": True,
    }
    if not token:
        payload.update({"ok": False, "reason": "missing replicate api token"})
        return _with_metadata(payload)
    payload.update({"ok": True, "note": "dry-run"})
    return _with_metadata(payload)


def poll(job_id: str, cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    _config_with_defaults(cfg)
    return _with_metadata(
        {
            "ok": True,
            "status": "done",
            "job_id": job_id or "mock-replicate-1",
            "artifacts": [],
        }
    )


__all__ = [
    "ALIASES",
    "CAPABILITIES",
    "DOCS_URL",
    "ENV_KEYS",
    "FEATURE_FLAG",
    "LAST_CHECKED",
    "PRICING_URL",
    "health",
    "metadata",
    "poll",
    "submit",
]
