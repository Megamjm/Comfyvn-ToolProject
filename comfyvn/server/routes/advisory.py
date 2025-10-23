from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.advisory.policy import gate_status, get_ack_record, set_ack
from comfyvn.config import feature_flags
from comfyvn.core.policy_gate import policy_gate
from comfyvn.policy.enforcer import policy_enforcer

DISCLAIMER_TEXT = (
    "ComfyVN surfaces advisory warnings for licensing, attribution, and content "
    "sensitivity. The platform does not block your workflow; acknowledging this "
    "notice confirms you will review findings and take responsibility for how "
    "imports, assets, and exports are used or shared.\n\n"
    "Learn more in docs/ADVISORY_EXPORT.md and docs/LEGAL_LIABILITY.md. Keep the "
    "provenance reports that accompany assets and exports so you can demonstrate "
    "how findings were reviewed."
)


class DisclaimerAckRequest(BaseModel):
    user: str = Field(
        "anonymous",
        description="Identifier recorded with the disclaimer acknowledgement.",
    )
    name: str | None = Field(
        None,
        description="Optional display name; falls back to the supplied user value when omitted.",
    )
    notes: str | None = Field(
        None, description="Optional notes stored alongside the acknowledgement record."
    )


class AdvisoryScanRequest(BaseModel):
    action: str = Field(
        "export.bundle.preview",
        description="Action identifier used for advisory logging and provenance notes.",
    )
    bundle: Dict[str, Any] = Field(
        default_factory=dict,
        description="Bundle payload (scenes/assets/licenses) evaluated by advisory scanners.",
    )
    override: bool = Field(
        False,
        description="Flag an override request; still recorded with the advisory log entry.",
    )
    source: Optional[str] = Field(
        None,
        description="Override the advisory log source descriptor (defaults to action/bundle context).",
    )
    include_debug: bool = Field(
        False,
        description="Include debug descriptors (bundle summary, enforcement source) in the response.",
    )


class AdvisoryFinding(BaseModel):
    category: str = Field(
        ...,
        description="Coarse grouping for UI filters (license, sfw, unknown).",
    )
    severity: str = Field(
        ...,
        description="Severity derived from advisory scanners (info, warn, block).",
    )
    message: str = Field(..., description="Human-readable advisory message.")
    kind: Optional[str] = Field(
        None, description="Raw advisory kind emitted by the scanner."
    )
    target: Optional[str] = Field(
        None, description="Target identifier (scene, asset, license, etc.)."
    )
    detail: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scanner-provided structured context for the finding.",
    )
    issue_id: Optional[str] = Field(
        None, description="Persisted advisory issue identifier when available."
    )


advisory_router = APIRouter(prefix="/api/advisory", tags=["Advisory"])
legacy_policy_router = APIRouter(prefix="/api/policy", tags=["Advisory (legacy)"])
router = APIRouter(tags=["Advisory"])
router.include_router(advisory_router)
router.include_router(legacy_policy_router)


def _disclaimer_links(status_payload: Dict[str, Any]) -> Dict[str, str]:
    disclaimer = status_payload.get("disclaimer") or {}
    links = disclaimer.get("links") or {}
    if not links:
        from comfyvn.core.policy_gate import DISCLAIMER_LINKS

        links = dict(DISCLAIMER_LINKS)
    return links


def _disclaimer_payload(message: Optional[str] = None) -> Dict[str, Any]:
    status = gate_status()
    ack_record = get_ack_record()
    evaluation = policy_gate.evaluate_action("advisory.disclaimer")
    detail_message = message or (
        "Review the advisory disclaimer before proceeding with imports or exports."
        if status.requires_ack
        else "Advisory disclaimer acknowledged; findings will be recorded for transparency."
    )
    payload = {
        "acknowledged": bool(ack_record.get("ack")),
        "status": status.to_dict(),
        "ack": ack_record,
        "message": detail_message,
        "links": _disclaimer_links(evaluation),
        "version": (evaluation.get("disclaimer") or {}).get("version", "v1"),
        "text": DISCLAIMER_TEXT,
    }
    return payload


def _map_category(entry: Mapping[str, Any]) -> str:
    kind = str(entry.get("kind") or "").lower()
    detail = entry.get("detail") or {}
    if isinstance(detail, Mapping):
        detail_kind = str(detail.get("kind") or detail.get("category") or "").lower()
    else:
        detail_kind = ""
    if (
        any(
            token in kind
            for token in ("license", "copyright", "policy", "ip", "attribution")
        )
        or "license" in detail_kind
    ):
        return "license"
    if any(token in kind for token in ("nsfw", "sfw", "content", "safety")):
        return "sfw"
    if isinstance(detail, Mapping) and str(detail.get("content_warning") or "").strip():
        return "sfw"
    return "unknown"


def _normalise_finding(entry: Dict[str, Any]) -> AdvisoryFinding:
    category = _map_category(entry)
    severity = str(entry.get("level") or entry.get("severity") or "info").lower()
    detail = entry.get("detail")
    if not isinstance(detail, dict):
        detail = {}
    return AdvisoryFinding(
        category=category,
        severity=severity,
        message=entry.get("message") or "",
        kind=entry.get("kind"),
        target=entry.get("target_id") or detail.get("target"),
        detail=detail,
        issue_id=entry.get("issue_id"),
    )


def _categorise_counts(findings: Iterable[AdvisoryFinding]) -> Dict[str, int]:
    counts = {"license": 0, "sfw": 0, "unknown": 0}
    for entry in findings:
        if entry.category not in counts:
            counts["unknown"] += 1
        else:
            counts[entry.category] += 1
    return counts


@advisory_router.get(
    "/disclaimer",
    summary="Read advisory disclaimer text and acknowledgement status.",
)
def read_disclaimer() -> Dict[str, Any]:
    return {"ok": True, **_disclaimer_payload()}


@advisory_router.post(
    "/ack",
    summary="Acknowledge the advisory disclaimer.",
)
def acknowledge_disclaimer(payload: DisclaimerAckRequest = Body(...)) -> Dict[str, Any]:
    set_ack(True, user=payload.user, name=payload.name, notes=payload.notes)
    return {
        "ok": True,
        **_disclaimer_payload(
            "Disclaimer acknowledged. Advisory findings remain informational warnings."
        ),
    }


@advisory_router.post(
    "/scan",
    summary="Evaluate a bundle payload with advisory scanners.",
)
def scan_bundle(payload: AdvisoryScanRequest = Body(...)) -> Dict[str, Any]:
    if not feature_flags.is_enabled("enable_advisory", default=False):
        raise HTTPException(status_code=403, detail="enable_advisory disabled")

    action = payload.action or "export.bundle.preview"
    bundle = payload.bundle or {}
    enforcement = policy_enforcer.enforce(
        action,
        bundle,
        override=payload.override,
        source=payload.source or "api.advisory.scan",
    ).to_dict()

    findings_raw = enforcement.get("findings") or []
    findings = [_normalise_finding(dict(entry)) for entry in findings_raw]
    counts = _categorise_counts(findings)
    disclaimer = _disclaimer_payload()

    response: Dict[str, Any] = {
        "ok": True,
        "acknowledged": disclaimer["acknowledged"],
        "disclaimer": {
            "message": disclaimer["message"],
            "links": disclaimer["links"],
            "version": disclaimer["version"],
            "acknowledged": disclaimer["acknowledged"],
        },
        "findings": [entry.model_dump() for entry in findings],
        "counts": counts,
        "gate": enforcement.get("gate") or {},
        "log_path": enforcement.get("log_path"),
        "warnings": enforcement.get("warnings") or [],
        "info": enforcement.get("info") or [],
    }
    if payload.include_debug:
        response["bundle"] = enforcement.get("bundle") or {}
        response["source"] = enforcement.get("source")
    return response


@legacy_policy_router.get("/ack", summary="[Legacy] Read acknowledgement status")
def legacy_read_ack() -> Dict[str, Any]:
    payload = _disclaimer_payload()
    status = payload["status"]
    record = payload["ack"]
    return {
        "ack": payload["acknowledged"],
        "status": status,
        "name": record.get("name"),
        "at": record.get("at"),
        "message": payload["message"],
        "allow_override": bool(status.get("warn_override_enabled", True)),
    }


@legacy_policy_router.post(
    "/ack",
    summary="[Legacy] Persist acknowledgement for liability gate",
)
def legacy_write_ack(payload: DisclaimerAckRequest = Body(...)) -> Dict[str, Any]:
    return acknowledge_disclaimer(payload)


@legacy_policy_router.delete(
    "/ack",
    summary="[Legacy] Clear acknowledgement (development/testing only)",
)
def legacy_clear_ack() -> Dict[str, Any]:
    set_ack(False, user="system", notes="cleared via legacy API")
    payload = _disclaimer_payload("Disclaimer acknowledgement cleared.")
    status = payload["status"]
    record = payload["ack"]
    return {
        "ack": payload["acknowledged"],
        "status": status,
        "name": record.get("name"),
        "at": record.get("at"),
        "message": payload["message"],
        "allow_override": bool(status.get("warn_override_enabled", True)),
    }
