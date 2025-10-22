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
from typing import Any, Dict, Iterable, List, Mapping, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.config.feature_flags import is_enabled
from comfyvn.remote import installer
from comfyvn.security import secrets_store

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


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _sanitize_mapping(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k): v for k, v in data.items() if v is not None}


def _extract_secret_payload(
    host: str, secret_block: Mapping[str, Any]
) -> Dict[str, Any]:
    provider = str(secret_block.get("provider") or "").strip()
    if not provider:
        raise HTTPException(status_code=400, detail="secrets.provider required")

    entry_key = (
        secret_block.get("key") or secret_block.get("entry") or secret_block.get("id")
    )
    entry_value = str(entry_key).strip() if entry_key else None

    try:
        provider_payload = secrets_store.default_store().get(provider)
    except secrets_store.SecretStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not isinstance(provider_payload, Mapping):
        return {}

    result: Dict[str, Any] = {}
    defaults = provider_payload.get("defaults")
    if isinstance(defaults, Mapping):
        result.update(_sanitize_mapping(defaults))

    hosts = provider_payload.get("hosts")
    if isinstance(hosts, Mapping):
        for key in (entry_value, host, "default"):
            if not key:
                continue
            entry = hosts.get(key)
            if isinstance(entry, Mapping):
                result.update(_sanitize_mapping(entry))
                break

    direct = provider_payload.get(entry_value) if entry_value else None
    if isinstance(direct, Mapping):
        result.update(_sanitize_mapping(direct))

    host_direct = provider_payload.get(host)
    if isinstance(host_direct, Mapping):
        result.update(_sanitize_mapping(host_direct))

    for field in (
        "user",
        "username",
        "port",
        "identity",
        "identity_file",
        "ssh_command",
        "scp_command",
        "connect_timeout",
        "env",
    ):
        if field in provider_payload and field not in {"defaults", "hosts"}:
            value = provider_payload[field]
            if value is not None:
                result[field] = value

    return result


def _merge_ssh_payload(host: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ssh_block = payload.get("ssh") if isinstance(payload.get("ssh"), Mapping) else {}
    secrets_block = payload.get("secrets") or payload.get("credentials")

    merged: Dict[str, Any] = {}
    if isinstance(secrets_block, Mapping) and secrets_block:
        merged.update(_extract_secret_payload(host, secrets_block))
    if isinstance(ssh_block, Mapping) and ssh_block:
        merged.update(_sanitize_mapping(ssh_block))

    if not merged:
        return None

    # strip helper keys that are not part of SSHConfig
    for helper_key in ("provider", "key", "entry", "id", "record_only", "probe"):
        merged.pop(helper_key, None)

    return merged


def _runtime_from_payload(
    host: str, payload: Dict[str, Any], *, dry_run: bool
) -> Optional[installer.InstallRuntime]:
    ssh_payload = _merge_ssh_payload(host, payload)
    if not ssh_payload:
        return None

    record_only = dry_run or _coerce_bool(payload.get("record_only"), False)
    ssh_section = payload.get("ssh")
    if isinstance(ssh_section, Mapping):
        record_only = record_only or _coerce_bool(ssh_section.get("record_only"), False)

    probe_enabled = _coerce_bool(payload.get("probe"), True)
    if isinstance(ssh_section, Mapping) and "probe" in ssh_section:
        probe_enabled = _coerce_bool(ssh_section.get("probe"), True)

    try:
        runtime = installer.build_runtime(
            host,
            ssh_payload,
            enable_probe=bool(probe_enabled),
            record_only=bool(record_only),
        )
    except installer.RuntimeConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return runtime


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

    dry_run = _coerce_bool(payload.get("dry_run"), False)

    runtime: Optional[installer.InstallRuntime] = None
    try:
        runtime = _runtime_from_payload(host_str, payload, dry_run=dry_run)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        plan_entries = installer.plan(host_str, modules, runtime=runtime)
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
            "failed": [],
        }

    LOGGER.info(
        "[remote-installer] apply plan for host=%s modules=%s", host_str, modules
    )
    result = installer.apply(
        host_str, plan_entries, log_hook=log_writer, runtime=runtime
    )
    result["ok"] = True
    return result


@router.get("/status", summary="Fetch remote installer status")
async def remote_status(
    host: Optional[str] = Query(None, description="Hostname to inspect")
) -> Dict[str, Any]:
    if not is_enabled("enable_remote_installer"):
        raise HTTPException(status_code=403, detail="remote installer disabled")

    if host:
        try:
            status = installer.read_status(host)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "host": host,
            "status": status,
            "status_path": str(installer.status_path(host)),
        }

    return {"ok": True, "hosts": installer.list_statuses()}
