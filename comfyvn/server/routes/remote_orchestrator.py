from __future__ import annotations

"""
Remote installer orchestration routes.

Expose module registry discovery plus a simple `/api/remote/install` endpoint
that records orchestrated install steps and status metadata per host.  The
installer itself performs a dry recording so tests remain deterministic; the
log output can be replayed by a higher-level executor when actual SSH calls
are required.
"""

import logging
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, Body, HTTPException

from comfyvn.config.feature_flags import is_enabled
from comfyvn.remote import installer

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remote", tags=["Remote Installer"])


def _coerce_modules(raw: Any) -> List[str]:
    if raw is None:
        raise ValueError("modules field is required")
    if isinstance(raw, str):
        if raw.strip().lower() == "all":
            return [entry["id"] for entry in installer.list_modules()]
        return [raw]
    if isinstance(raw, Iterable):
        items: List[str] = []
        for value in raw:
            text = str(value or "").strip()
            if text:
                items.append(text)
        if not items:
            raise ValueError("modules list is empty")
        return items
    raise ValueError("modules must be a string or list of strings")


@router.get("/modules", summary="List remote installer modules")
async def remote_modules() -> Dict[str, Any]:
    return {"modules": installer.list_modules()}


@router.post("/install", summary="Plan and record remote installs")
async def remote_install(
    payload: Dict[str, Any] = Body(
        ...,
        description=(
            "Remote install payload with `host`, `modules`, and optional `dry_run`."
        ),
    )
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    if not is_enabled("enable_remote_installer"):
        raise HTTPException(status_code=403, detail="remote installer disabled")

    host = payload.get("host") or payload.get("hostname")
    if not host or not str(host).strip():
        raise HTTPException(status_code=400, detail="host required")
    host_str = str(host).strip()

    try:
        modules = _coerce_modules(payload.get("modules"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dry_run = bool(payload.get("dry_run"))

    try:
        plan_entries = installer.plan(host_str, modules)
    except KeyError as exc:
        raise HTTPException(
            status_code=400, detail=f"unknown module '{exc.args[0]}'"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_writer, log_path = installer.open_log(host_str)
    status_path = installer.status_path(host_str)

    if dry_run:
        LOGGER.info(
            "[remote-installer] dry-run for host=%s modules=%s", host_str, modules
        )
        return {
            "ok": True,
            "host": host_str,
            "status": "dry_run",
            "plan": plan_entries,
            "log_path": str(log_path),
            "status_path": str(status_path),
            "registry": installer.list_modules(),
        }

    LOGGER.info(
        "[remote-installer] apply plan for host=%s modules=%s", host_str, modules
    )
    result = installer.apply(host_str, plan_entries, log_hook=log_writer)
    result["ok"] = True
    return result
