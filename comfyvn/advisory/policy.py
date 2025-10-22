"""Convenience helpers around the persisted liability gate."""

from __future__ import annotations

from typing import Optional

from comfyvn.core.policy_gate import PolicyStatus, policy_gate


def gate_status() -> PolicyStatus:
    """Return the current liability gate status."""
    return policy_gate.status()


def evaluate_action(action: str, *, override: bool = False) -> dict:
    """
    Evaluate ``action`` against the liability gate and return a copy of the payload.

    The extra copy avoids leaking internal state to callers that may mutate the
    dictionary for logging or response shaping.
    """

    gate = dict(policy_gate.evaluate_action(action, override=override))
    gate.setdefault("action", action)
    return gate


def get_ack() -> bool:
    """Return ``True`` when the legal acknowledgement has been recorded."""
    return gate_status().ack_legal_v1


def set_ack(
    value: bool = True,
    *,
    user: str = "anonymous",
    notes: Optional[str] = None,
) -> PolicyStatus:
    """Record or clear the acknowledgement flag and return the resulting status."""
    return (
        policy_gate.acknowledge(user=user, notes=notes)
        if value
        else policy_gate.reset()
    )


def require_ack(
    action: str,
    *,
    override: bool = False,
    message: Optional[str] = None,
) -> dict:
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
