"""Liability gate persistence helpers.

This module keeps the runtime ``policy_gate`` in sync with a persisted
acknowledgement flag stored at ``config/policy_ack.json``.  Legacy helpers
(``evaluate_action`` / ``require_ack``) remain available for existing callers.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from comfyvn.core.policy_gate import PolicyStatus, policy_gate

# Phase 2/2 Project Integration Chat — Live Fix Stub
_ACK_PATH = Path("config/policy_ack.json")
_SYNC_NOTES = "synced from policy_ack.json"


def _coerce_ack_record(payload: Any) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    if isinstance(payload, bool):
        return {"ack": bool(payload)}
    if isinstance(payload, Mapping):
        record: Dict[str, Any] = {"ack": bool(payload.get("ack", False))}
        name = payload.get("name") or payload.get("user")
        if isinstance(name, str):
            name = name.strip()
            if name:
                record["name"] = name
        notes = payload.get("notes")
        if isinstance(notes, str):
            notes = notes.strip()
            if notes:
                record["notes"] = notes
        timestamp = payload.get("at") or payload.get("timestamp")
        if timestamp is not None:
            try:
                record["at"] = float(timestamp)
            except (TypeError, ValueError):
                pass
        return record
    return None


def _read_ack_file() -> Optional[Dict[str, Any]]:
    if not _ACK_PATH.exists():
        return None
    try:
        payload = json.loads(_ACK_PATH.read_text(encoding="utf-8") or "{}")
        record = _coerce_ack_record(payload)
        if record is not None:
            return record
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def _write_ack_file(record: Mapping[str, Any]) -> None:
    _ACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        delete=False, dir=str(_ACK_PATH.parent), prefix=_ACK_PATH.stem, suffix=".tmp"
    )
    payload: Dict[str, Any] = {"ack": bool(record.get("ack", False))}
    if record.get("name"):
        payload["name"] = record["name"]
    if record.get("notes"):
        payload["notes"] = record["notes"]
    if record.get("at") is not None:
        try:
            payload["at"] = float(record["at"])
        except (TypeError, ValueError):
            payload["at"] = time.time()
    try:
        tmp.write(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, _ACK_PATH)


def _ensure_gate_sync(record: Mapping[str, Any]) -> PolicyStatus:
    """Ensure the in-memory policy gate reflects the persisted ack flag."""
    status = policy_gate.status()
    target_ack = bool(record.get("ack"))
    name = str(record.get("name") or "").strip()
    if target_ack:
        needs_ack = (
            not status.ack_legal_v1
            or (name and status.ack_user != name)
            or (status.ack_timestamp is None and record.get("at") is not None)
        )
        if needs_ack:
            return policy_gate.acknowledge(
                user=name or "system",
                notes=record.get("notes") or _SYNC_NOTES,
                timestamp=record.get("at"),
            )
        return status
    if status.ack_legal_v1:
        return policy_gate.reset()
    return status


def _maybe_upgrade_ack_file(
    status: PolicyStatus, record: Optional[Dict[str, Any]]
) -> None:
    if not record:
        return
    if not bool(record.get("ack")):
        if record.get("name") or record.get("notes"):
            cleaned = {"ack": False, "at": record.get("at")}
            _write_ack_file(cleaned)
        return
    upgraded = dict(record)
    needs_write = False
    if status.ack_user and not upgraded.get("name"):
        upgraded["name"] = status.ack_user
        needs_write = True
    if status.ack_timestamp and not upgraded.get("at"):
        upgraded["at"] = status.ack_timestamp
        needs_write = True
    if needs_write:
        _write_ack_file(upgraded)


def gate_status() -> PolicyStatus:
    """Return the current liability gate status, syncing from disk if required."""
    persisted = _read_ack_file()
    if persisted is not None:
        status = _ensure_gate_sync(persisted)
        _maybe_upgrade_ack_file(status, persisted)
    else:
        status = policy_gate.status()
    return status


def evaluate_action(action: str, *, override: bool = False) -> Dict[str, Any]:
    """
    Evaluate ``action`` against the liability gate, returning a shallow copy.
    """

    gate = dict(policy_gate.evaluate_action(action, override=override))
    gate.setdefault("action", action)
    return gate


def get_ack_record() -> Dict[str, Any]:
    """Return the persisted acknowledgement metadata (ack flag, name, timestamp)."""
    status = gate_status()
    record = _read_ack_file()
    if record is None:
        return {
            "ack": bool(status.ack_legal_v1),
            "name": status.ack_user,
            "at": status.ack_timestamp,
        }
    payload = dict(record)
    if payload.get("ack"):
        payload.setdefault("name", status.ack_user)
        payload.setdefault("at", status.ack_timestamp)
    else:
        payload.pop("name", None)
        payload.pop("notes", None)
        payload["ack"] = False
    return payload


def get_ack() -> bool:
    """Return ``True`` when the legal acknowledgement has been recorded."""
    return bool(get_ack_record().get("ack"))


def set_ack(
    value: bool = True,
    *,
    user: str = "anonymous",
    name: Optional[str] = None,
    notes: Optional[str] = None,
) -> PolicyStatus:
    """Persist the acknowledgement flag and return the resulting status."""
    ack = bool(value)
    if ack:
        display_name = str(name or user or "anonymous").strip() or "anonymous"
        status = policy_gate.acknowledge(user=display_name, notes=notes)
        record: Dict[str, Any] = {
            "ack": True,
            "name": status.ack_user or display_name,
            "at": status.ack_timestamp or time.time(),
        }
        if notes:
            record["notes"] = notes
        _write_ack_file(record)
        return status
    status = policy_gate.reset()
    _write_ack_file({"ack": False, "at": status.ack_timestamp})
    return status


def require_ack(
    action: str,
    *,
    override: bool = False,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate ``action`` against the liability gate.

    Raises ``RuntimeError`` when the action is blocked due to a missing
    acknowledgement. The gate evaluation payload is returned otherwise.
    """
    gate = evaluate_action(action, override=override)
    if gate.get("requires_ack") and not gate.get("allow", False):
        raise RuntimeError(
            message
            or "Policy acknowledgement required. POST /api/policy/ack before retrying."
        )
    return gate


def require_ack_or_raise(action: str, *, override: bool = False) -> Dict[str, Any]:
    """
    Raise ``PermissionError`` when the liability gate blocks ``action``.

    This helper mirrors :func:`require_ack` but surfaces a distinct error type for
    callers that map missing acknowledgements to HTTP 423 / UI prompts.
    """

    try:
        return require_ack(action, override=override)
    except RuntimeError as exc:
        raise PermissionError(str(exc)) from exc
