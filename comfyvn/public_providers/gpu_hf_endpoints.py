from __future__ import annotations

"""
Hugging Face Inference Endpoints adapter.

Provides metadata, health checks, and dry-run submit/poll helpers so Studio
integrations can validate request shapes without incurring usage.
"""

from typing import Any, Dict, Mapping

from . import provider_secrets, resolve_credential

PROVIDER_ID = "hf_inference_endpoints"
DISPLAY_NAME = "Hugging Face Inference Endpoints"
FEATURE_FLAG = "enable_public_gpu"
PRICING_URL = "https://huggingface.co/docs/inference-endpoints/pricing"
DOCS_URL = "https://huggingface.co/docs/inference-endpoints/index"
LAST_CHECKED = "2025-02-17"
ENV_KEYS: tuple[str, ...] = (
    "HF_API_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "HF_INFERENCE_ENDPOINTS_TOKEN",
)
SECRET_KEYS: tuple[str, ...] = ("api_token", "token")
ALIASES: tuple[str, ...] = (
    "hf",
    "huggingface",
    "huggingface_inference",
    "hf_endpoints",
    "hf-inference",
)
CAPABILITIES: Dict[str, Any] = {
    "supports": ["managed_inference", "autoscaling", "private_networking"],
    "gpu_families": ["NVIDIA_T4", "A10G", "A100_80GB"],
    "billing": "per-minute with 1 minute minimum",
    "regions": ["us-east-1", "us-west-2", "eu-west-1"],
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
    raw = config.get("token") or config.get("api_token")
    return str(raw or "").strip()


def _config_with_defaults(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    data: Dict[str, object] = {}
    data.update(provider_secrets(PROVIDER_ID))
    if cfg:
        data.update(dict(cfg))
    return data


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
            {"ok": False, "reason": "missing hf api token", "dry_run": True}
        )
    return _with_metadata({"ok": True, "credential": "present"})


def submit(
    job: Mapping[str, object], cfg: Mapping[str, object] | None = None
) -> Dict[str, object]:
    config = _config_with_defaults(cfg)
    token = _token_from(config)
    endpoint = str(job.get("endpoint") or job.get("name") or "mock-endpoint")
    payload = {
        "job": dict(job),
        "endpoint": endpoint,
        "id": "mock-hf-endpoint-1",
        "dry_run": True,
    }
    if not token:
        payload.update({"ok": False, "reason": "missing hf api token"})
        return _with_metadata(payload)
    payload.update({"ok": True, "note": "dry-run"})
    return _with_metadata(payload)


def poll(job_id: str, cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    _config_with_defaults(cfg)
    return _with_metadata(
        {
            "ok": True,
            "status": "done",
            "job_id": job_id or "mock-hf-endpoint-1",
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
