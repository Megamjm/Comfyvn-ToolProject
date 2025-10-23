from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.compute.providers import get_default_registry
from comfyvn.compute.providers_echo import EchoAdapter
from comfyvn.compute.providers_runpod import RunPodAdapter
from comfyvn.compute.providers_unraid import UnraidAdapter
from comfyvn.core import compute_providers as generic_providers
from comfyvn.core.task_registry import task_registry

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["Compute Providers (runtime)"])

_REGISTRY = get_default_registry()
_REMOTE_ROOT = Path("data/remote")


def _resolve_provider(provider_id: str) -> Dict[str, Any]:
    entry = _REGISTRY.get(provider_id)
    if not entry:
        raise HTTPException(status_code=404, detail="provider not found")
    return entry


def _provider_signature(entry: Dict[str, Any]) -> Tuple[str, str]:
    provider_id = str(entry.get("id") or "").lower()
    service = str(entry.get("service") or entry.get("kind") or "").lower()
    return provider_id, service


def _adapter_for(entry: Dict[str, Any]):
    provider_id, service = _provider_signature(entry)
    if "runpod" in {provider_id, service}:
        return "runpod", RunPodAdapter.from_provider(entry)
    if "unraid" in provider_id or service in {"unraid", "lan", "ssh_unraid"}:
        return "unraid", UnraidAdapter.from_provider(entry)
    if "echo" in {provider_id, service}:
        return "echo", EchoAdapter.from_provider(entry)
    return "generic", None


async def _generic_health(entry: Dict[str, Any]) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: generic_providers.health(entry))


def _workspace_path_hint(payload: Dict[str, Any]) -> Optional[Path]:
    workspace_hint = payload.get("workspace") or payload.get("workspace_path")
    if not workspace_hint:
        return None
    try:
        path = Path(str(workspace_hint)).expanduser()
    except Exception:  # pragma: no cover - defensive
        return None
    return path


def _timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _log_writer(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(message: str) -> None:
        line = f"[{_timestamp()}] {message}"
        with log_path.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")

    return _write


@router.get("/health")
async def providers_health(
    provider_id: Optional[str] = Query(
        None,
        alias="id",
        description="Optional provider identifier; returns all when omitted.",
    )
) -> Dict[str, Any]:
    entries: Iterable[Dict[str, Any]]
    if provider_id:
        entries = [_resolve_provider(provider_id)]
    else:
        entries = _REGISTRY.list()

    results: List[Dict[str, Any]] = []
    for entry in entries:
        kind, adapter = _adapter_for(entry)
        if kind == "runpod":
            status = await adapter.health()  # type: ignore[union-attr]
        elif kind == "unraid":
            status = await adapter.health()  # type: ignore[union-attr]
        elif kind == "echo":
            status = await adapter.health()  # type: ignore[union-attr]
        else:
            status = await _generic_health(entry)
        status["provider_id"] = entry.get("id")
        status["provider_name"] = entry.get("name")
        results.append(status)

    if provider_id:
        status = results[0]
        return {"ok": bool(status.get("ok")), "status": status}
    return {"ok": any(row.get("ok") for row in results), "results": results}


@router.get("/quota")
async def providers_quota(
    provider_id: str = Query(..., alias="id", description="Provider identifier"),
) -> Dict[str, Any]:
    entry = _resolve_provider(provider_id)
    kind, adapter = _adapter_for(entry)
    if kind == "runpod":
        result = await adapter.fetch_quota()  # type: ignore[union-attr]
    elif kind == "unraid":
        result = await adapter.fetch_quota()  # type: ignore[union-attr]
    elif kind == "echo":
        result = await adapter.fetch_quota()  # type: ignore[union-attr]
    else:
        result = {"ok": False, "error": "quota inspection not supported"}
    result["provider_id"] = provider_id
    return result


@router.get("/templates")
async def providers_templates(
    provider_id: str = Query(..., alias="id", description="Provider identifier"),
) -> Dict[str, Any]:
    entry = _resolve_provider(provider_id)
    kind, adapter = _adapter_for(entry)
    if kind == "runpod":
        result = await adapter.fetch_templates()  # type: ignore[union-attr]
    elif kind == "unraid":
        result = await adapter.fetch_templates()  # type: ignore[union-attr]
    elif kind == "echo":
        result = await adapter.fetch_templates()  # type: ignore[union-attr]
    else:
        result = {"ok": False, "error": "template enumeration not available"}
    result["provider_id"] = provider_id
    return result


@router.post("/bootstrap")
async def providers_bootstrap(
    payload: Dict[str, Any] = Body(
        ...,
        description="Bootstrap request body containing provider id and optional workspace path.",
    )
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    provider_id = payload.get("id") or payload.get("provider_id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider id required")
    provider_id = str(provider_id)

    entry = _resolve_provider(provider_id)
    kind, adapter = _adapter_for(entry)
    if adapter is None:
        raise HTTPException(
            status_code=400,
            detail=f"bootstrap not supported for {entry.get('service')}",
        )

    workspace = _workspace_path_hint(payload)
    if workspace and not workspace.exists():
        LOGGER.warning("Workspace hint %s missing; ignoring", workspace)
        workspace = None

    job_payload = {
        "provider_id": provider_id,
        "provider": entry,
        "workspace": str(workspace) if workspace else None,
    }
    job_message = f"Bootstrap {entry.get('name') or provider_id}"

    job_output_dir = (_REMOTE_ROOT / provider_id / uuid.uuid4().hex).resolve()
    log_path = job_output_dir / "bootstrap.log"
    log_writer = _log_writer(log_path)

    job_id = task_registry.register(
        "provider.bootstrap",
        job_payload,
        message=job_message,
        meta={"provider_id": provider_id, "logs_path": str(log_path)},
    )
    task_registry.update(job_id, status="running", progress=0.05, message=job_message)

    job_output_dir.mkdir(parents=True, exist_ok=True)

    async def _run_bootstrap():
        try:
            result = await adapter.bootstrap(  # type: ignore[union-attr]
                output_dir=job_output_dir,
                workspace=workspace,
                log_hook=log_writer,
            )
        except Exception as exc:  # pragma: no cover - remote dependent
            LOGGER.error("Provider bootstrap failed: %s", exc)
            log_writer(f"Bootstrap failed: {exc}")
            task_registry.update(
                job_id,
                status="error",
                progress=1.0,
                message=f"Bootstrap failed: {exc}",
            )
            raise HTTPException(
                status_code=500, detail=f"bootstrap failed: {exc}"
            ) from exc

        ok = bool(result.get("ok"))
        message = "Bootstrap complete" if ok else "Bootstrap finished with warnings"
        task_registry.update(
            job_id,
            status="done" if ok else "error",
            progress=1.0,
            message=message,
        )
        log_writer(message)
        return result

    result = await _run_bootstrap()

    artifacts_raw = result.get("artifacts") or []
    normalized_artifacts: List[str] = []
    for item in artifacts_raw:
        try:
            candidate = Path(str(item))
        except Exception:
            continue
        if not candidate.is_absolute():
            candidate = (job_output_dir / candidate).resolve()
        normalized_artifacts.append(str(candidate))

    summary = {
        "ok": bool(result.get("ok")),
        "job": job_id,
        "provider": {"id": provider_id, "name": entry.get("name")},
        "logs_path": str(log_path),
        "output_dir": str(job_output_dir),
        "artifacts": normalized_artifacts,
        "details": result.get("details"),
    }

    # Persist bootstrap metadata for later review.
    metadata_path = job_output_dir / "bootstrap_summary.json"
    metadata_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return summary
