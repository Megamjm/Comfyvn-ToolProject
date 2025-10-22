from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
)

from comfyvn.advisory import scanner
from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.core.policy_gate import PolicyGate, policy_gate

LOGGER = logging.getLogger("comfyvn.policy.enforcer")

DEFAULT_LOG_DIR = Path(os.getenv("COMFYVN_POLICY_LOG_DIR", "logs/policy"))
DEFAULT_LOG_FILE = "enforcer.jsonl"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _coerce_mapping(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _bundle_descriptor(bundle: Any) -> Dict[str, Any]:
    data = _coerce_mapping(bundle)
    meta: Dict[str, Any] = {}
    if not data:
        return meta
    project_id = data.get("project_id") or data.get("project")
    if project_id:
        meta["project_id"] = str(project_id)
    timeline_id = data.get("timeline_id") or data.get("timeline")
    if timeline_id:
        meta["timeline_id"] = str(timeline_id)
    source = None
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        meta["metadata"] = dict(metadata)
        source = metadata.get("source")
    elif metadata:
        meta["metadata"] = metadata
    scenes = data.get("scenes")
    if isinstance(scenes, Mapping):
        meta["scene_count"] = len(scenes)
    assets = data.get("assets")
    assets_count = None
    if isinstance(assets, Sequence) and not isinstance(assets, (str, bytes)):
        assets_count = len(list(assets))
    if assets_count is not None:
        meta["asset_count"] = assets_count
    licenses = data.get("licenses")
    if isinstance(licenses, Sequence) and not isinstance(licenses, (str, bytes)):
        meta["license_count"] = len(list(licenses))
    if source:
        meta["source"] = source
    return meta


def _normalise_level(entry: Mapping[str, Any]) -> str:
    level = str(entry.get("level") or "").lower()
    if level in {"info", "warn", "block"}:
        return level
    severity = str(entry.get("severity") or "").lower()
    if severity in {"block", "error", "critical"}:
        return "block"
    if severity == "warn":
        return "warn"
    return "info"


def _normalise_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(entry)
    payload["level"] = _normalise_level(entry)
    payload.setdefault("severity", payload["level"])
    detail = entry.get("detail")
    if isinstance(detail, MutableMapping):
        payload["detail"] = dict(detail)
    return payload


@dataclass
class EnforcementResult:
    """Structured payload returned by the policy enforcer."""

    action: str
    allow: bool
    gate: Dict[str, Any]
    counts: Dict[str, int]
    findings: List[Dict[str, Any]] = field(default_factory=list)
    blocked: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    info: List[Dict[str, Any]] = field(default_factory=list)
    bundle: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())
    log_path: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "allow": self.allow,
            "gate": self.gate,
            "counts": self.counts,
            "findings": self.findings,
            "blocked": self.blocked,
            "warnings": self.warnings,
            "info": self.info,
            "bundle": self.bundle,
            "timestamp": self.timestamp,
            "log_path": self.log_path,
            "source": self.source,
        }


class PolicyEnforcer:
    """
    Evaluate advisory findings for import/export actions and persist enforcement logs.
    """

    def __init__(
        self,
        *,
        log_dir: Path | str | None = None,
        gate: PolicyGate | None = None,
        enabled: Optional[bool] = None,
    ) -> None:
        resolved_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        self.log_dir = _ensure_dir(resolved_dir)
        self.log_path = self.log_dir / DEFAULT_LOG_FILE
        self.policy_gate = gate or policy_gate
        self._feature_override = enabled

    def _feature_enabled(self) -> bool:
        if self._feature_override is not None:
            return bool(self._feature_override)
        return feature_flags.is_enabled("enable_policy_enforcer", default=True)

    def _serialise_record(self, payload: EnforcementResult) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_path.as_posix()
        payload.log_path = log_path
        record = payload.to_dict()
        record["timestamp"] = payload.timestamp
        record["log_path"] = log_path
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to persist policy enforcement record: %s", exc)

    def _scan_findings(
        self, bundle: Any, *, findings: Optional[Iterable[Mapping[str, Any]]]
    ) -> List[Dict[str, Any]]:
        if findings is not None:
            return [_normalise_entry(entry) for entry in findings]
        if bundle is None:
            return []
        try:
            entries = scanner.scan(bundle)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Policy scanner failed: %s", exc)
            return []
        return [_normalise_entry(entry) for entry in entries]

    def enforce(
        self,
        action: str,
        bundle: Any = None,
        *,
        findings: Optional[Iterable[Mapping[str, Any]]] = None,
        override: bool = False,
        source: Optional[str] = None,
    ) -> EnforcementResult:
        gate_status = self.policy_gate.evaluate_action(action, override=override)
        enabled = self._feature_enabled()
        findings_list = (
            self._scan_findings(bundle, findings=findings) if enabled else []
        )
        blocked = [entry for entry in findings_list if entry["level"] == "block"]
        warnings = [entry for entry in findings_list if entry["level"] == "warn"]
        info = [entry for entry in findings_list if entry["level"] == "info"]

        allow = bool(gate_status.get("allow", True))
        if enabled and blocked:
            allow = False

        counts = {
            "info": len(info),
            "warn": len(warnings),
            "block": len(blocked),
        }

        descriptor = _bundle_descriptor(bundle)
        if source:
            descriptor["source"] = source
        elif "source" not in descriptor:
            descriptor["source"] = action

        result = EnforcementResult(
            action=action,
            allow=allow,
            gate=gate_status,
            counts=counts,
            findings=findings_list,
            blocked=blocked,
            warnings=warnings,
            info=info,
            bundle=descriptor,
            source=descriptor.get("source"),
        )

        if enabled:
            self._serialise_record(result)
            if allow:
                LOGGER.info(
                    "Policy enforcement action=%s allow counts=%s",
                    action,
                    counts,
                )
            else:
                LOGGER.warning(
                    "Policy enforcement blocked action=%s counts=%s",
                    action,
                    counts,
                )
            try:
                result.log_path = self.log_path.as_posix()
            except Exception:  # pragma: no cover - defensive
                result.log_path = None
            try:
                modder_hooks.emit(
                    "on_policy_enforced",
                    {
                        "action": action,
                        "allow": allow,
                        "counts": counts,
                        "blocked": blocked,
                        "warnings": warnings,
                        "info": info,
                        "bundle": descriptor,
                        "log_path": result.log_path,
                        "timestamp": result.timestamp,
                    },
                )
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Modder hook dispatch failed: %s", exc)

        return result


policy_enforcer = PolicyEnforcer()

__all__ = ["PolicyEnforcer", "EnforcementResult", "policy_enforcer"]
