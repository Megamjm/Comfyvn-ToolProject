"""Liability gate persistence helpers.

This module keeps the runtime ``policy_gate`` in sync with a persisted
acknowledgement flag stored at ``config/policy_ack.json``.  Legacy helpers
(``evaluate_action`` / ``require_ack``) remain available for existing callers.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from comfyvn.core.policy_gate import PolicyStatus, policy_gate

# Phase 2/2 Project Integration Chat — Live Fix Stub
_ACK_PATH = Path("config/policy_ack.json")
_SYNC_NOTES = "synced from policy_ack.json"


def _read_ack_file() -> Optional[bool]:
    if not _ACK_PATH.exists():
        return None
    try:
        payload = json.loads(_ACK_PATH.read_text(encoding="utf-8") or "{}")
        return bool(payload.get("ack", False))
    except Exception:
        return None


def _write_ack_file(ack: bool) -> None:
    _ACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        delete=False, dir=str(_ACK_PATH.parent), prefix=_ACK_PATH.stem, suffix=".tmp"
    )
    try:
        tmp.write(json.dumps({"ack": bool(ack)}).encode("utf-8"))
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, _ACK_PATH)


def _ensure_gate_sync(target_ack: bool) -> PolicyStatus:
    """Ensure the in-memory policy gate reflects the persisted ack flag."""
    status = policy_gate.status()
    if bool(status.ack_legal_v1) == bool(target_ack):
        return status
    if target_ack:
        return policy_gate.acknowledge(user="system", notes=_SYNC_NOTES)
    return policy_gate.reset()


def gate_status() -> PolicyStatus:
    """Return the current liability gate status, syncing from disk if required."""
    persisted = _read_ack_file()
    if persisted is not None:
        status = _ensure_gate_sync(persisted)
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


def get_ack() -> bool:
    """Return ``True`` when the legal acknowledgement has been recorded."""
    persisted = _read_ack_file()
    if persisted is not None:
        return bool(persisted)
    return bool(policy_gate.status().ack_legal_v1)


def set_ack(
    value: bool = True,
    *,
    user: str = "anonymous",
    notes: Optional[str] = None,
) -> PolicyStatus:
    """Persist the acknowledgement flag and return the resulting status."""
    ack = bool(value)
    _write_ack_file(ack)
    if ack:
        return policy_gate.acknowledge(user=user, notes=notes)
    return policy_gate.reset()


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
