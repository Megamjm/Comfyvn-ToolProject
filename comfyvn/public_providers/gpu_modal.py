from __future__ import annotations

"""
Modal Labs API adapter.

Documents capabilities and exposes dry-run helpers for job submission and poll
workflows.  Real executions remain opt-in once credentials and flags are set.
"""

from typing import Any, Dict, Mapping

from . import provider_secrets, resolve_credential

PROVIDER_ID = "modal"
DISPLAY_NAME = "Modal"
FEATURE_FLAG = "enable_public_gpu"
PRICING_URL = "https://modal.com/pricing"
DOCS_URL = "https://modal.com/docs"
LAST_CHECKED = "2025-02-17"
ENV_KEYS: tuple[str, ...] = (
    "MODAL_API_TOKEN",
    "MODAL_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
)
SECRET_KEYS: tuple[str, ...] = ("api_token", "token", "token_id", "token_secret")
ALIASES: tuple[str, ...] = ("modal", "modal.com")
CAPABILITIES: Dict[str, Any] = {
    "supports": ["serverless", "schedules", "volumes", "webhooks"],
    "gpu_families": ["A10G", "L4", "A100_80GB"],
    "billing": "per-second with 1-minute minimum",
    "regions": ["us-west-1", "us-east-1", "eu-west-1"],
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


def _config_with_defaults(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    data: Dict[str, Any] = {}
    data.update(provider_secrets(PROVIDER_ID))
    if cfg:
        data.update(dict(cfg))
    return data


def _credentials(config: Mapping[str, object]) -> Dict[str, str] | None:
    token = resolve_credential(
        PROVIDER_ID,
        env_keys=("MODAL_API_TOKEN", "MODAL_TOKEN"),
        secret_keys=("api_token", "token"),
    )
    if token:
        return {"kind": "api_token", "token": token.strip()}

    token_id = str(config.get("token_id") or "").strip()
    token_secret = str(config.get("token_secret") or "").strip()
    if token_id and token_secret:
        return {
            "kind": "token_pair",
            "token_id": token_id,
            "token_secret": token_secret,
        }

    # Capture env fallbacks from resolve_credential by requesting raw keys.
    fallback_id = resolve_credential(
        PROVIDER_ID,
        env_keys=("MODAL_TOKEN_ID",),
        secret_keys=("token_id",),
    )
    fallback_secret = resolve_credential(
        PROVIDER_ID,
        env_keys=("MODAL_TOKEN_SECRET",),
        secret_keys=("token_secret",),
    )
    if fallback_id and fallback_secret:
        return {
            "kind": "token_pair",
            "token_id": fallback_id.strip(),
            "token_secret": fallback_secret.strip(),
        }
    return None


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
    creds = _credentials(config)
    if not creds:
        return _with_metadata(
            {
                "ok": False,
                "reason": "missing modal token or token pair",
                "dry_run": True,
            }
        )
    return _with_metadata({"ok": True, "credential": creds["kind"]})


def submit(
    job: Mapping[str, object], cfg: Mapping[str, object] | None = None
) -> Dict[str, object]:
    config = _config_with_defaults(cfg)
    creds = _credentials(config)
    function = str(job.get("function") or job.get("app") or "modal.function")
    payload = {
        "job": dict(job),
        "function": function,
        "id": "mock-modal-1",
        "dry_run": True,
    }
    if not creds:
        payload.update({"ok": False, "reason": "missing modal token or token pair"})
        return _with_metadata(payload)
    payload.update({"ok": True, "credential": creds["kind"], "note": "dry-run"})
    return _with_metadata(payload)


def poll(job_id: str, cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    _config_with_defaults(cfg)
    return _with_metadata(
        {
            "ok": True,
            "status": "done",
            "job_id": job_id or "mock-modal-1",
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
