from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

DEFAULT_LOG_DIR = Path(os.getenv("COMFYVN_POLICY_LOG_DIR", "logs/policy"))
DEFAULT_LOG_FILE = "enforcer.jsonl"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:  # pragma: no cover - defensive
        return 0.0


@dataclass
class AuditEvent:
    action: str
    allow: bool
    counts: Dict[str, int]
    timestamp: float
    source: Optional[str]
    log_path: Optional[str]
    bundle: Dict[str, object]
    blocked: List[Dict[str, object]]
    warnings: List[Dict[str, object]]


class PolicyAudit:
    """Timeline reader for policy enforcement events."""

    def __init__(self, *, log_dir: Path | str | None = None) -> None:
        resolved_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        self.log_dir = _ensure_dir(resolved_dir)
        self.log_path = self.log_dir / DEFAULT_LOG_FILE

    def _iter_events(self) -> Iterable[AuditEvent]:
        if not self.log_path.exists():
            return []
        events: List[AuditEvent] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:  # pragma: no cover - defensive
                continue
            events.append(
                AuditEvent(
                    action=str(payload.get("action") or "unknown"),
                    allow=bool(payload.get("allow", False)),
                    counts=dict(payload.get("counts") or {}),
                    timestamp=_safe_float(payload.get("timestamp")),
                    source=payload.get("source"),
                    log_path=payload.get("log_path"),
                    bundle=dict(payload.get("bundle") or {}),
                    blocked=list(payload.get("blocked") or []),
                    warnings=list(payload.get("warnings") or []),
                )
            )
        events.sort(key=lambda item: item.timestamp, reverse=True)
        return events

    def list_events(
        self,
        limit: int = 50,
        *,
        action: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        events = []
        for event in self._iter_events():
            if action and event.action != action:
                continue
            events.append(
                {
                    "action": event.action,
                    "allow": event.allow,
                    "counts": event.counts,
                    "timestamp": event.timestamp,
                    "source": event.source,
                    "log_path": event.log_path or self.log_path.as_posix(),
                    "bundle": event.bundle,
                    "blocked": event.blocked,
                    "warnings": event.warnings,
                }
            )
            if len(events) >= limit:
                break
        return events

    def summary(self) -> Dict[str, object]:
        events = list(self._iter_events())
        totals = {"info": 0, "warn": 0, "block": 0}
        per_action: Dict[str, Dict[str, int]] = {}
        for event in events:
            for level, value in event.counts.items():
                try:
                    totals[level] += int(value)
                except KeyError:
                    totals[level] = int(value)
            per_action.setdefault(event.action, {"runs": 0, "blocks": 0})
            per_action[event.action]["runs"] += 1
            if not event.allow:
                per_action[event.action]["blocks"] += 1
        return {"totals": totals, "per_action": per_action, "events": len(events)}

    def export_report(self, *, destination: Optional[Path | str] = None) -> Path:
        events = [dict(event) for event in self.list_events(limit=500)]
        payload = {
            "generated_at": time.time(),
            "events": events,
            "summary": self.summary(),
        }
        if destination:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = time.strftime("%Y%m%d-%H%M%S")
            path = self.log_dir / f"policy_audit_{ts}.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path


policy_audit = PolicyAudit()

__all__ = ["PolicyAudit", "policy_audit"]
