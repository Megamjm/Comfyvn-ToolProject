from __future__ import annotations

"""
RunPod public adapter.

This is intentionally a compile-safe stub: until a valid API token is supplied
the functions return dry-run payloads so Studio tooling can verify request
shapes without dispatching real GPU jobs.
"""

from typing import Dict, Mapping

from . import provider_secrets


def _config_with_defaults(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    payload: Dict[str, object] = {}
    payload.update(provider_secrets("runpod"))
    if cfg:
        payload.update(dict(cfg))
    return payload


def health(cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    """
    Validate RunPod credentials.  Returns ``{"ok": True}`` when a token is
    present; otherwise, surfaces a dry-run reason.
    """

    config = _config_with_defaults(cfg)
    token = str(config.get("token") or config.get("api_key") or "").strip()
    if not token:
        return {"ok": False, "reason": "missing token", "dry_run": True}
    # We do not call the network yet; simply acknowledge the token exists.
    return {"ok": True, "dry_run": True}


def submit(
    job: Mapping[str, object], cfg: Mapping[str, object] | None = None
) -> Dict[str, object]:
    """
    Submit a job sketch to RunPod.  This stub records the intent and returns a
    deterministic mock identifier so UI flows can continue.
    """

    config = _config_with_defaults(cfg)
    token = str(config.get("token") or config.get("api_key") or "").strip()
    payload = {"job": dict(job), "dry_run": True}
    if not token:
        payload.update({"ok": False, "reason": "missing token"})
        return payload
    payload.update({"ok": True, "id": "mock-runpod-1", "note": "dry-run"})
    return payload


def poll(job_id: str, cfg: Mapping[str, object] | None = None) -> Dict[str, object]:
    """
    Poll the status of a previously submitted job.  Dry-run results always
    complete successfully so downstream asset pipelines can exercise success
    handlers without waiting on external systems.
    """

    _config_with_defaults(cfg)  # ensures consistent merge / placeholder
    return {
        "ok": True,
        "status": "done",
        "job_id": job_id,
        "artifacts": [],
        "dry_run": True,
    }


__all__ = ["health", "poll", "submit"]
