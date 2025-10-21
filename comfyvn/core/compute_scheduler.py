from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from comfyvn.core.compute_advisor import advise as compute_advise
from comfyvn.core.compute_providers import send_job
from comfyvn.core.compute_registry import get_provider_registry
from comfyvn.core.gpu_manager import get_gpu_manager

LOGGER = logging.getLogger(__name__)

GPU_MANAGER = get_gpu_manager()
REGISTRY = get_provider_registry()


def _resolve_workload(job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    job = job or {}
    workload = job.get("workload")
    if isinstance(workload, dict):
        return workload
    return job


def _resolve_requirements(
    job: Dict[str, Any], workload: Dict[str, Any]
) -> Dict[str, Any]:
    requirements = workload.get("requirements")
    if isinstance(requirements, dict):
        return requirements
    if isinstance(job.get("requirements"), dict):
        return job["requirements"]  # type: ignore[index]
    return {}


def choose_device(
    job: Optional[Dict[str, Any]], context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Decide where a job should execute based on policy and advisor heuristics.

    Returns a dictionary containing the final `choice` (cpu|gpu|remote),
    the selected device id, policy metadata, advisor rationale, and resolved
    remote provider information when applicable.
    """

    context = context or {}
    queue_depth = int(context.get("queue_depth") or 0)
    remote_threshold = int(context.get("remote_threshold") or 3)
    prefer_remote = bool(context.get("prefer_remote", False))
    hardware_override = bool(context.get("hardware_override", False))
    prefer_device: Optional[str] = context.get("prefer_device")

    job_payload = job or {}
    workload = _resolve_workload(job_payload)
    requirements = _resolve_requirements(job_payload, workload)

    if hardware_override:
        prefer_device = "cpu"

    if not prefer_remote and queue_depth and queue_depth >= remote_threshold:
        prefer_remote = True

    advisor = compute_advise(
        GPU_MANAGER,
        workload=workload,
        prefer_remote=prefer_remote,
        hardware_override=hardware_override,
    )

    remote_candidate = advisor.get("remote_candidate") or {}
    remote_id = remote_candidate.get("id")
    if prefer_remote and not prefer_device and remote_id:
        prefer_device = f"remote:{remote_id}"

    selection = GPU_MANAGER.select_device(
        prefer=prefer_device, requirements=requirements
    )
    device_id = selection.get("device") or selection.get("id") or "cpu"
    device_kind = selection.get("kind") or (
        "remote"
        if device_id.startswith("remote:")
        else "gpu" if device_id != "cpu" else "cpu"
    )

    device_info = None
    for device in GPU_MANAGER.list_all(refresh=False):
        if device.get("id") == device_id:
            device_info = device
            break

    choice = "cpu"
    remote_provider: Optional[Dict[str, Any]] = None
    if device_kind == "remote" or device_id.startswith("remote:"):
        choice = "remote"
        provider_id = selection.get("provider_id") or (
            device_id.split(":", 1)[1] if ":" in device_id else None
        )
        if provider_id and GPU_MANAGER.registry:
            provider_entry = GPU_MANAGER.registry.get(provider_id)
            if provider_entry:
                remote_provider = {
                    "id": provider_entry.get("id"),
                    "name": provider_entry.get("name"),
                    "service": provider_entry.get("service"),
                    "base_url": provider_entry.get("base_url"),
                    "meta": provider_entry.get("meta"),
                }
    elif device_kind == "gpu" or device_id.startswith("cuda:") or device_id != "cpu":
        choice = "gpu"

    reason_parts: List[str] = []
    advisor_reason = advisor.get("reason")
    if isinstance(advisor_reason, str) and advisor_reason:
        reason_parts.append(advisor_reason)
    policy_reason = selection.get("reason")
    policy_mode = selection.get("policy")
    if policy_mode and policy_reason:
        reason_parts.append(f"Policy {policy_mode} ({policy_reason})")
    elif policy_reason:
        reason_parts.append(str(policy_reason))
    if choice == "remote" and remote_provider:
        reason_parts.append(
            f"Routing to remote provider '{remote_provider.get('name')}'"
        )

    reason = (
        "; ".join(reason_parts) if reason_parts else "No compute rationale provided."
    )

    decision: Dict[str, Any] = {
        "choice": choice,
        "device": device_id,
        "reason": reason,
        "selection": selection,
        "advisor": advisor,
        "queue_depth": queue_depth,
        "prefer_remote": prefer_remote,
        "hardware_override": hardware_override,
    }
    if remote_provider:
        decision["remote_provider"] = remote_provider
    if device_info:
        decision["device_info"] = device_info

    LOGGER.debug(
        "choose_device -> choice=%s device=%s policy=%s prefer_remote=%s queue=%s",
        choice,
        device_id,
        selection.get("policy"),
        prefer_remote,
        queue_depth,
    )
    return decision


def pick_and_send(settings: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy helper retained for compatibility with existing callers.

    Uses ``choose_device`` to resolve a provider and attempts to dispatch the
    payload. Remote providers rely on the compute registry while local jobs
    target the built-in ``local`` provider entry.
    """

    decision = choose_device(payload, context=settings)
    choice = decision.get("choice")
    provider_id: Optional[str] = None
    provider_entry: Optional[Dict[str, Any]] = None

    if choice == "remote":
        remote_info = decision.get("remote_provider") or {}
        provider_id = remote_info.get("id") or decision.get("selection", {}).get(
            "provider_id"
        )
    elif choice == "gpu":
        provider_id = "local"
    else:
        return {
            "ok": False,
            "error": "CPU-only execution is not supported via pick_and_send.",
            "decision": decision,
        }

    if not provider_id:
        return {
            "ok": False,
            "error": "Unable to resolve provider for job",
            "decision": decision,
        }

    provider_entry = REGISTRY.get(provider_id)
    if not provider_entry:
        return {
            "ok": False,
            "error": f"Provider '{provider_id}' not found",
            "decision": decision,
        }

    try:
        result = send_job(provider_entry, payload)
    except Exception as exc:  # pragma: no cover - network call
        LOGGER.warning("Dispatch failed for provider=%s: %s", provider_id, exc)
        return {
            "ok": False,
            "error": str(exc),
            "provider": provider_id,
            "decision": decision,
        }

    response = {
        "ok": bool(result.get("ok")),
        "provider": provider_id,
        "result": result,
        "decision": decision,
    }
    return response
