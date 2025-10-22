from __future__ import annotations

"""
Role and adapter orchestration helpers for ComfyVN.

This module provides a lightweight in-memory planner that maps high-level
storytelling roles (Narrator, MC, Antagonist, Extras) onto concrete language
model adapters.  The orchestrator is deterministic and intentionally
side-effect free with respect to external services so it can be exercised in
offline or test environments without network access.
"""

import hashlib
import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

RoleName = str


def _now() -> float:
    return time.time()


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _normalize_role(role: str) -> str:
    return _safe_text(role or "Narrator", "Narrator").title()


class OfflineAdapter:
    """
    Deterministic offline adapter used when no remote model is configured.

    The adapter does not perform network calls.  Replies are generated from the
    supplied message and a short digest of the context payload so repeated calls
    with identical inputs return identical outputs.
    """

    adapter_id: str = "offline.local"
    model_id: str = "codex/offline-narrator"
    device_id: str = "cpu"

    def describe(self) -> Dict[str, Any]:
        return {
            "id": self.adapter_id,
            "label": "Offline Codex Narrator",
            "model": self.model_id,
            "device": self.device_id,
            "capabilities": {
                "chat": True,
                "offline": True,
                "deterministic": True,
            },
        }

    def _context_summary(self, context: Iterable[Dict[str, Any]]) -> Tuple[str, str]:
        speakers: List[str] = []
        highlights: List[str] = []
        for entry in context:
            speaker = _safe_text(entry.get("speaker") or entry.get("name"), "Narrator")
            text = _safe_text(entry.get("text") or entry.get("content"))
            if text:
                highlights.append(f"{speaker}: {text}")
            if speaker not in speakers:
                speakers.append(speaker)
        summary = " | ".join(highlights[-3:]) if highlights else ""
        roster = ", ".join(speakers[:6])
        return roster, summary

    def _estimate_tokens(self, message: str, summary: str) -> int:
        combined_len = len(message) + len(summary)
        rough_tokens = max(16, int(combined_len / 4) + 12)
        return min(2048, rough_tokens)

    def plan(
        self, role: str, message: str, context: Iterable[Dict[str, Any]]
    ) -> Dict[str, Any]:
        roster, summary = self._context_summary(context)
        tokens = self._estimate_tokens(message, summary)
        digest_source = f"{role.lower()}::{message}::{summary}"
        digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:8]
        return {
            "role": role,
            "adapter": self.adapter_id,
            "model": self.model_id,
            "device": self.device_id,
            "tokens": tokens,
            "summary": summary,
            "context_roster": roster,
            "digest": digest,
        }

    def generate(
        self, role: str, message: str, context: Iterable[Dict[str, Any]]
    ) -> Dict[str, Any]:
        plan = self.plan(role, message, context)
        roster = plan["context_roster"]
        summary = plan["summary"]
        message_text = message or "..."
        parts = []
        if summary:
            parts.append(f"Recent beats: {summary}")
        if roster:
            parts.append(f"Cast on stage: {roster}")
        payload = " • ".join(parts) if parts else "Scene is quiet."
        reply = (
            f"[offline:{plan['digest']}] {role} reflects on the scene. {payload} "
            f"Intent: {message_text}"
        ).strip()
        return {
            "reply": reply,
            "plan": plan,
            "tokens": plan["tokens"],
            "metadata": {
                "adapter": self.adapter_id,
                "model": self.model_id,
                "role": role,
                "deterministic": True,
            },
        }


@dataclass
class RoleAssignment:
    role: RoleName
    adapter: Optional[str] = None
    model: Optional[str] = None
    device: Optional[str] = None
    budget_tokens: int = 0
    budget_spent: int = 0
    sticky: bool = False
    session_id: Optional[str] = None
    created_at: float = field(default_factory=_now)
    last_used: Optional[float] = None
    status: str = "disabled"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "adapter": self.adapter,
            "model": self.model,
            "device": self.device,
            "budget": {
                "limit": self.budget_tokens,
                "spent": self.budget_spent,
                "remaining": max(self.budget_tokens - self.budget_spent, 0),
            },
            "sticky": self.sticky,
            "session_id": self.session_id,
            "status": self.status,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "metadata": dict(self.metadata),
        }


class RoleOrchestrator:
    """
    Maps narrative roles onto target adapters while tracking token budgets and
    sticky session assignments.
    """

    DEFAULT_ROLES: Tuple[str, ...] = ("Narrator", "MC", "Antagonist", "Extras")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._assignments: Dict[RoleName, RoleAssignment] = {
            role: RoleAssignment(role=role) for role in self.DEFAULT_ROLES
        }
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._offline = OfflineAdapter()
        self._session_counter = itertools.count(1)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _ensure_role(self, role: str) -> RoleAssignment:
        role_name = _normalize_role(role)
        if role_name not in self._assignments:
            self._assignments[role_name] = RoleAssignment(role=role_name)
        return self._assignments[role_name]

    def _next_session_id(self, role: str) -> str:
        return f"{role.lower()}-sess-{next(self._session_counter):04d}"

    def _resolve_target(self, assignment: RoleAssignment) -> Tuple[str, str, str, bool]:
        if assignment.adapter and assignment.status != "disabled":
            adapter = _safe_text(assignment.adapter)
            model = _safe_text(assignment.model, "default")
            device = _safe_text(assignment.device, "auto")
            return adapter, model, device, True
        offline = self._offline.describe()
        return offline["id"], offline["model"], offline["device"], False

    def _record_session(
        self,
        *,
        role: str,
        assignment: RoleAssignment,
        adapter: str,
        model: str,
        device: str,
        tokens: int,
    ) -> Dict[str, Any]:
        now = _now()
        if assignment.sticky and adapter != self._offline.adapter_id:
            if not assignment.session_id:
                assignment.session_id = self._next_session_id(role)
            session_id = assignment.session_id
        else:
            session_id = f"offline:{role.lower()}"
        record = self._sessions.get(session_id)
        if record is None:
            record = {
                "id": session_id,
                "role": role,
                "adapter": adapter,
                "model": model,
                "device": device,
                "sticky": bool(
                    assignment.sticky and adapter != self._offline.adapter_id
                ),
                "messages": 0,
                "tokens": 0,
                "created_at": now,
                "last_used": now,
                "status": "warm",
            }
            self._sessions[session_id] = record
        record["messages"] += 1
        record["tokens"] += max(tokens, 0)
        record["last_used"] = now
        return dict(record)

    def _budget_window(self, assignment: RoleAssignment, tokens: int) -> Dict[str, Any]:
        budget_limit = max(int(assignment.budget_tokens or 0), 0)
        spent = max(int(assignment.budget_spent or 0), 0)
        remaining = budget_limit - spent
        post = remaining - tokens if budget_limit else None
        permitted = True
        if budget_limit and post is not None and post < 0:
            permitted = False
        return {
            "limit": budget_limit,
            "spent": spent,
            "remaining": max(remaining, 0),
            "would_spend": tokens,
            "would_remaining": max(post if post is not None else remaining - tokens, 0),
            "permitted": permitted,
        }

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "roles": [
                    assignment.to_dict() for assignment in self._assignments.values()
                ],
                "offline": self._offline.describe(),
                "sessions": list(self._sessions.values()),
                "timestamp": _now(),
            }

    def assign(
        self,
        role: str,
        *,
        adapter: Optional[str] = None,
        model: Optional[str] = None,
        device: Optional[str] = None,
        budget_tokens: Optional[int] = None,
        sticky: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            assignment = self._ensure_role(role)
            adapter_clean = _safe_text(adapter, "")
            if not adapter_clean or adapter_clean.lower() in {
                "off",
                "none",
                "disabled",
            }:
                assignment.adapter = None
                assignment.model = None
                assignment.device = None
                assignment.status = "disabled"
                assignment.session_id = None
                assignment.sticky = False
                assignment.metadata.clear()
            else:
                assignment.adapter = adapter_clean
                assignment.model = _safe_text(model, assignment.model)
                assignment.device = _safe_text(device, assignment.device)
                assignment.status = "armed"
                if sticky is None:
                    # preserve previous sticky preference when re-arming
                    sticky = assignment.sticky
                assignment.sticky = bool(sticky)
                if not assignment.sticky:
                    assignment.session_id = None
            if sticky is not None and assignment.adapter:
                assignment.sticky = bool(sticky)
                if not assignment.sticky:
                    assignment.session_id = None
            if budget_tokens is not None:
                assignment.budget_tokens = max(int(budget_tokens), 0)
                if assignment.budget_tokens == 0:
                    assignment.budget_spent = 0
                else:
                    assignment.budget_spent = min(
                        assignment.budget_spent, assignment.budget_tokens
                    )
            if metadata is not None:
                assignment.metadata = dict(metadata)
            assignment.last_used = _now()
            return assignment.to_dict()

    def clear_role(self, role: str) -> Dict[str, Any]:
        return self.assign(role, adapter=None, model=None, device=None, sticky=False)

    def plan(
        self,
        *,
        role: str,
        message: str = "",
        context: Optional[Iterable[Dict[str, Any]]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        ctx = list(context or [])
        role_name = _normalize_role(role)
        with self._lock:
            assignment = self._ensure_role(role_name)
            adapter, model, device, assigned = self._resolve_target(assignment)
            offline = adapter == self._offline.adapter_id
            planning_context = (
                ctx if ctx else [{"speaker": "System", "text": "No context"}]
            )
            offline_plan = self._offline.plan(role_name, message, planning_context)
            tokens = offline_plan["tokens"]
            budget = self._budget_window(assignment, tokens)
            session_info: Optional[Dict[str, Any]] = None
            if not dry_run:
                if not budget["permitted"]:
                    assignment.status = "exhausted"
                else:
                    assignment.last_used = _now()
                    if assigned:
                        assignment.status = "active"
                    else:
                        assignment.status = "offline"
                    assignment.budget_spent += tokens if assignment.budget_tokens else 0
                    session_info = self._record_session(
                        role=role_name,
                        assignment=assignment,
                        adapter=adapter,
                        model=model,
                        device=device,
                        tokens=tokens,
                    )
            return {
                "role": role_name,
                "adapter": adapter,
                "model": model,
                "device": device,
                "assigned": assigned,
                "offline": offline,
                "plan_tokens": tokens,
                "budget": budget,
                "session": session_info,
                "dry_run": dry_run,
                "timestamp": _now(),
                "context": {
                    "roster": offline_plan["context_roster"],
                    "summary": offline_plan["summary"],
                    "digest": offline_plan["digest"],
                },
            }

    def simulate(
        self,
        *,
        role: str,
        message: str = "",
        context: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        ctx = list(context or [])
        planning = self.plan(role=role, message=message, context=ctx, dry_run=True)
        offline_result = self._offline.generate(role, message, ctx)
        result = {
            "reply": offline_result["reply"],
            "tokens": offline_result["tokens"],
            "adapter": planning["adapter"],
            "model": planning["model"],
            "device": planning["device"],
            "metadata": offline_result["metadata"],
            "plan": planning,
        }
        return result

    def route(
        self,
        *,
        role: str,
        message: str = "",
        context: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        ctx = list(context or [])
        simulation = self.simulate(role=role, message=message, context=ctx)
        with self._lock:
            plan = self.plan(role=role, message=message, context=ctx, dry_run=False)
        simulation["plan"] = plan
        simulation["budget"] = plan["budget"]
        simulation["session"] = plan.get("session")
        return simulation

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "timestamp": _now(),
                "roles": [
                    assignment.to_dict() for assignment in self._assignments.values()
                ],
                "sessions": list(self._sessions.values()),
                "offline": self._offline.describe(),
            }

    def reset_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
        return False


# Shared singleton orchestrator
ROLE_ORCHESTRATOR = RoleOrchestrator()


def orchestrator() -> RoleOrchestrator:
    return ROLE_ORCHESTRATOR


__all__ = ["ROLE_ORCHESTRATOR", "RoleOrchestrator", "RoleAssignment", "orchestrator"]
