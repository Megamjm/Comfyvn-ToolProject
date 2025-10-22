from __future__ import annotations

"""
Narrator orchestration routes.

Implements Observe → Propose → Apply rails with a deterministic proposal queue,
ring-buffer rollback, and integration with the role-to-adapter orchestrator.
"""

import copy
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.config.feature_flags import is_enabled
from comfyvn.core import modder_hooks
from comfyvn.core.modder_hooks import HookSpec
from comfyvn.llm.orchestrator import ROLE_ORCHESTRATOR

LOGGER = logging.getLogger(__name__)

MAX_TURNS_PER_NODE = 3
HISTORY_LIMIT = 12
DEFAULT_ROLE = "Narrator"


def _now() -> float:
    return time.time()


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _register_hook_specs() -> None:
    """Ensure narrator hooks are exposed through the modder bus."""

    if "on_narrator_proposal" not in modder_hooks.HOOK_SPECS:
        modder_hooks.HOOK_SPECS["on_narrator_proposal"] = HookSpec(
            name="on_narrator_proposal",
            description="Fires when the narrator proposer records a draft decision.",
            payload_fields={
                "scene_id": "Scene identifier provided by the caller.",
                "node_id": "Canonical node identifier supplied in the payload.",
                "proposal_id": "Deterministic proposal identifier.",
                "choice_id": "Choice identifier suggested by the narrator.",
                "vars_patch": "Variable patch dictionary staged for application.",
                "rationale": "Short free-form rationale string for the decision.",
                "turn_index": "Turn index within the active node (1-based).",
                "mode": "Narrator mode when the proposal was generated.",
                "timestamp": "Unix timestamp (seconds).",
            },
            ws_topic="modder.on_narrator_proposal",
            rest_event="on_narrator_proposal",
        )
    if "on_narrator_apply" not in modder_hooks.HOOK_SPECS:
        modder_hooks.HOOK_SPECS["on_narrator_apply"] = HookSpec(
            name="on_narrator_apply",
            description="Emitted when a queued narrator proposal is approved and applied.",
            payload_fields={
                "scene_id": "Scene identifier tied to the narrator session.",
                "node_id": "Canonical node identifier when the proposal was applied.",
                "proposal_id": "Identifier of the proposal that was applied.",
                "choice_id": "Choice identifier that was committed (if any).",
                "vars_patch": "Patch dictionary that was merged into the variables.",
                "turn_index": "Turn index that was consumed.",
                "timestamp": "Unix timestamp (seconds).",
                "rolled_back": "True when the apply surfaced from a rollback replay.",
            },
            ws_topic="modder.on_narrator_apply",
            rest_event="on_narrator_apply",
        )


_register_hook_specs()


@dataclass
class NarratorProposal:
    id: str
    scene_id: str
    node_id: str
    mode: str
    role: str
    turn_index: int
    message: str
    narration: str
    rationale: str
    choice_id: Optional[str]
    vars_patch: Dict[str, Any]
    plan: Dict[str, Any]
    created_at: float
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, position: Optional[int] = None) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "scene_id": self.scene_id,
            "node_id": self.node_id,
            "mode": self.mode,
            "role": self.role,
            "turn_index": self.turn_index,
            "message": self.message,
            "narration": self.narration,
            "rationale": self.rationale,
            "choice_id": self.choice_id,
            "vars_patch": copy.deepcopy(self.vars_patch),
            "plan": copy.deepcopy(self.plan),
            "status": self.status,
            "created_at": self.created_at,
            "metadata": copy.deepcopy(self.metadata),
            "context": copy.deepcopy(self.context),
        }
        if position is not None:
            payload["position"] = position
        return payload


@dataclass
class NarratorSnapshot:
    node_id: str
    variables: Dict[str, Any]
    turn_counts: Dict[str, int]
    last_choice: Optional[str]
    proposal_id: Optional[str]
    created_at: float


@dataclass
class NarratorSession:
    scene_id: str
    node_id: str
    mode: str = "observe"
    role: str = DEFAULT_ROLE
    active: bool = True
    halted: bool = False
    pov: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    history: deque[NarratorSnapshot] = field(
        default_factory=lambda: deque(maxlen=HISTORY_LIMIT)
    )
    queue: List[str] = field(default_factory=list)
    proposals: Dict[str, NarratorProposal] = field(default_factory=dict)
    turn_counts: Dict[str, int] = field(default_factory=dict)
    proposal_counter: int = 0
    last_context: List[Dict[str, Any]] = field(default_factory=list)
    last_choice_applied: Optional[str] = None


class NarratorManager:
    """In-memory narrator session manager (per scene)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, NarratorSession] = {}

    # -------------------------- Internal helpers -------------------------- #
    def _session_key(self, scene_id: str) -> str:
        return _safe_text(scene_id, "default")

    def _ensure_session(self, scene_id: str, node_id: str) -> NarratorSession:
        key = self._session_key(scene_id)
        session = self._sessions.get(key)
        if session is None or session.node_id != node_id:
            session = NarratorSession(scene_id=scene_id, node_id=node_id)
            session.turn_counts[node_id] = session.turn_counts.get(node_id, 0)
            session.history.append(
                NarratorSnapshot(
                    node_id=node_id,
                    variables=copy.deepcopy(session.variables),
                    turn_counts=dict(session.turn_counts),
                    last_choice=session.last_choice_applied,
                    proposal_id=None,
                    created_at=_now(),
                )
            )
            self._sessions[key] = session
        return session

    def _capture_snapshot(
        self, session: NarratorSession, *, proposal_id: Optional[str]
    ) -> None:
        session.history.append(
            NarratorSnapshot(
                node_id=session.node_id,
                variables=copy.deepcopy(session.variables),
                turn_counts=dict(session.turn_counts),
                last_choice=session.last_choice_applied,
                proposal_id=proposal_id,
                created_at=_now(),
            )
        )

    def _serialize_queue(self, session: NarratorSession) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for idx, proposal_id in enumerate(session.queue, start=1):
            proposal = session.proposals.get(proposal_id)
            if not proposal:
                continue
            items.append(proposal.to_dict(position=idx))
        return items

    def _apply_patch(self, session: NarratorSession, patch: Dict[str, Any]) -> None:
        def _merge(target: Dict[str, Any], updates: Dict[str, Any]) -> None:
            for key, value in updates.items():
                if (
                    isinstance(value, dict)
                    and isinstance(target.get(key), dict)
                    and key not in {"$replace", "$delete"}
                ):
                    _merge(target[key], value)
                    continue
                if key == "$replace" and isinstance(value, dict):
                    for replace_key, replace_value in value.items():
                        target[replace_key] = replace_value
                    continue
                if key == "$delete":
                    delete_keys = value if isinstance(value, (list, tuple)) else [value]
                    for delete_key in delete_keys:
                        target.pop(str(delete_key), None)
                    continue
                target[key] = value

        _merge(session.variables, copy.deepcopy(patch))

    def _status_payload(self, session: NarratorSession) -> Dict[str, Any]:
        return {
            "scene_id": session.scene_id,
            "node_id": session.node_id,
            "mode": session.mode,
            "role": session.role,
            "active": session.active and not session.halted,
            "halted": session.halted,
            "turn_counts": dict(session.turn_counts),
            "queue": self._serialize_queue(session),
            "history_size": len(session.history),
            "last_choice": session.last_choice_applied,
            "pov": session.pov,
            "variables": copy.deepcopy(session.variables),
            "timestamp": _now(),
        }

    # ---------------------------- Public actions -------------------------- #
    def set_mode(
        self,
        *,
        scene_id: str,
        node_id: str,
        mode: str,
        context: Optional[List[Dict[str, Any]]] = None,
        variables: Optional[Dict[str, Any]] = None,
        pov: Optional[str] = None,
        reset_queue: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            session = self._ensure_session(scene_id, node_id)
            lower_mode = _safe_text(mode or "observe").lower()
            if session.node_id != node_id:
                session.node_id = node_id
            if reset_queue or lower_mode == "observe":
                session.queue.clear()
                session.proposals.clear()
                session.turn_counts[node_id] = session.turn_counts.get(node_id, 0)
                session.history.clear()
                session.history.append(
                    NarratorSnapshot(
                        node_id=node_id,
                        variables=copy.deepcopy(variables or session.variables),
                        turn_counts=dict(session.turn_counts),
                        last_choice=session.last_choice_applied,
                        proposal_id=None,
                        created_at=_now(),
                    )
                )
            if variables is not None:
                session.variables = copy.deepcopy(variables)
            if context is not None:
                session.last_context = copy.deepcopy(context)
            if pov is not None:
                session.pov = _safe_text(pov)
            session.mode = lower_mode
            session.halted = lower_mode in {"stop", "stopped"}
            session.active = not session.halted
            return self._status_payload(session)

    def propose(
        self,
        *,
        scene_id: str,
        node_id: str,
        message: str,
        context: Optional[List[Dict[str, Any]]] = None,
        choices: Optional[Iterable[Dict[str, Any]]] = None,
        rationale: Optional[str] = None,
        role: str = DEFAULT_ROLE,
    ) -> Dict[str, Any]:
        with self._lock:
            session = self._ensure_session(scene_id, node_id)
            if session.halted:
                raise HTTPException(status_code=409, detail="narrator session halted")
            applied_turns = session.turn_counts.get(node_id, 0)
            pending_turns = sum(
                1
                for pid in session.queue
                if session.proposals.get(pid)
                and session.proposals[pid].status == "pending"
                and session.proposals[pid].node_id == node_id
            )
            if applied_turns + pending_turns >= MAX_TURNS_PER_NODE:
                raise HTTPException(
                    status_code=409,
                    detail=f"turn cap reached for node {node_id} (max={MAX_TURNS_PER_NODE})",
                )

            ctx = context if context is not None else session.last_context
            ctx_copy = copy.deepcopy(ctx or [])
            message_text = _safe_text(message, "Advance the scene.")
            simulation = ROLE_ORCHESTRATOR.simulate(
                role=role, message=message_text, context=ctx_copy
            )

            choice_id: Optional[str] = None
            if choices:
                valid_choices = [
                    choice
                    for choice in choices
                    if isinstance(choice, dict) and _safe_text(choice.get("id"))
                ]
                if valid_choices:
                    valid_choices.sort(
                        key=lambda item: (
                            int(item.get("priority", 0) or 0),
                            _safe_text(item.get("id")),
                        )
                    )
                    choice_id = _safe_text(valid_choices[0].get("id"))

            turn_index = applied_turns + pending_turns + 1
            vars_patch = {
                "$narrator": {
                    "scene_id": scene_id,
                    "node_id": node_id,
                    "turn": turn_index,
                    "choice_id": choice_id,
                    "digest": simulation["plan"]["context"]["digest"],
                }
            }
            rationale_text = _safe_text(
                rationale,
                f"Offline planner suggested choice '{choice_id or 'continue'}' "
                f"using adapter {simulation['plan']['adapter']}.",
            )

            session.proposal_counter += 1
            proposal_id = f"p{session.proposal_counter:04d}"
            proposal = NarratorProposal(
                id=proposal_id,
                scene_id=scene_id,
                node_id=node_id,
                mode=session.mode,
                role=role,
                turn_index=turn_index,
                message=message_text,
                narration=_safe_text(simulation["reply"]),
                rationale=rationale_text,
                choice_id=choice_id,
                vars_patch=vars_patch,
                plan=copy.deepcopy(simulation["plan"]),
                created_at=_now(),
                metadata={
                    "adapter": simulation["plan"]["adapter"],
                    "model": simulation["plan"]["model"],
                    "budget": simulation["plan"]["budget"],
                },
                context=ctx_copy,
            )
            session.proposals[proposal_id] = proposal
            session.queue.append(proposal_id)
            payload = proposal.to_dict(position=len(session.queue))
            modder_hooks.emit(
                "on_narrator_proposal",
                {
                    "scene_id": scene_id,
                    "node_id": node_id,
                    "proposal_id": proposal_id,
                    "choice_id": choice_id,
                    "vars_patch": copy.deepcopy(vars_patch),
                    "rationale": rationale_text,
                    "turn_index": turn_index,
                    "mode": session.mode,
                    "timestamp": proposal.created_at,
                },
            )
            status = self._status_payload(session)
            status["last_proposal"] = payload
            status["queue"] = self._serialize_queue(session)
            return status

    def apply(self, *, scene_id: str, proposal_id: str) -> Dict[str, Any]:
        with self._lock:
            key = self._session_key(scene_id)
            session = self._sessions.get(key)
            if not session:
                raise HTTPException(status_code=404, detail="narrator session missing")
            proposal = session.proposals.get(proposal_id)
            if not proposal:
                raise HTTPException(status_code=404, detail="proposal not found")
            if proposal.status == "applied":
                raise HTTPException(status_code=409, detail="proposal already applied")
            if proposal.status == "rolled_back":
                raise HTTPException(status_code=409, detail="proposal rolled back")

            self._capture_snapshot(session, proposal_id=proposal.id)
            self._apply_patch(session, proposal.vars_patch)
            session.turn_counts[session.node_id] = (
                session.turn_counts.get(session.node_id, 0) + 1
            )
            session.last_choice_applied = proposal.choice_id
            proposal.status = "applied"
            session.queue = [pid for pid in session.queue if pid != proposal_id]
            session.mode = "apply"
            timestamp = _now()
            modder_hooks.emit(
                "on_narrator_apply",
                {
                    "scene_id": scene_id,
                    "node_id": session.node_id,
                    "proposal_id": proposal.id,
                    "choice_id": proposal.choice_id,
                    "vars_patch": copy.deepcopy(proposal.vars_patch),
                    "turn_index": proposal.turn_index,
                    "timestamp": timestamp,
                    "rolled_back": False,
                },
            )
            status = self._status_payload(session)
            status["applied"] = proposal.to_dict()
            status["queue"] = self._serialize_queue(session)
            return status

    def stop(self, *, scene_id: str) -> Dict[str, Any]:
        with self._lock:
            key = self._session_key(scene_id)
            session = self._sessions.get(key)
            if not session:
                raise HTTPException(status_code=404, detail="narrator session missing")
            session.halted = True
            session.active = False
            session.mode = "stopped"
            return self._status_payload(session)

    def rollback(self, *, scene_id: str, steps: int) -> Dict[str, Any]:
        if steps <= 0:
            raise HTTPException(status_code=400, detail="steps must be positive")
        with self._lock:
            key = self._session_key(scene_id)
            session = self._sessions.get(key)
            if not session:
                raise HTTPException(status_code=404, detail="narrator session missing")
            restored: List[Dict[str, Any]] = []
            while steps and session.history:
                snapshot = session.history.pop()
                steps -= 1
                session.node_id = snapshot.node_id
                session.variables = copy.deepcopy(snapshot.variables)
                session.turn_counts = dict(snapshot.turn_counts)
                session.last_choice_applied = snapshot.last_choice
                if snapshot.proposal_id:
                    proposal = session.proposals.get(snapshot.proposal_id)
                    if proposal:
                        proposal.status = "rolled_back"
                        proposal.metadata["rolled_back_at"] = _now()
                        restored.append(proposal.to_dict())
                        modder_hooks.emit(
                            "on_narrator_apply",
                            {
                                "scene_id": scene_id,
                                "node_id": session.node_id,
                                "proposal_id": proposal.id,
                                "choice_id": proposal.choice_id,
                                "vars_patch": copy.deepcopy(proposal.vars_patch),
                                "turn_index": proposal.turn_index,
                                "timestamp": _now(),
                                "rolled_back": True,
                            },
                        )
            status = self._status_payload(session)
            status["rolled_back"] = restored
            status["queue"] = self._serialize_queue(session)
            return status

    def status(self, *, scene_id: str) -> Dict[str, Any]:
        with self._lock:
            key = self._session_key(scene_id)
            session = self._sessions.get(key)
            if not session:
                raise HTTPException(status_code=404, detail="narrator session missing")
            return self._status_payload(session)


MANAGER = NarratorManager()


def _require_enabled(flag_name: str, *, force: bool = False) -> None:
    if force:
        return
    if not is_enabled(flag_name, default=False):
        raise HTTPException(
            status_code=403, detail=f"feature flag '{flag_name}' is disabled"
        )


router = APIRouter(tags=["Narrator"])


@router.get("/api/narrator/status")
async def narrator_status(scene_id: str = Query(..., description="Active scene id")):
    _require_enabled("enable_narrator")
    return {"ok": True, "state": MANAGER.status(scene_id=scene_id)}


@router.post("/api/narrator/mode")
async def narrator_mode(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_narrator", force=force)

    scene_id = _safe_text(payload.get("scene_id"))
    node_id = _safe_text(payload.get("node_id"))
    if not scene_id or not node_id:
        raise HTTPException(status_code=400, detail="scene_id and node_id are required")
    mode = _safe_text(payload.get("mode") or "observe")
    context = payload.get("context")
    if context is not None and not isinstance(context, list):
        raise HTTPException(status_code=400, detail="context must be an array")
    variables = payload.get("variables")
    if variables is not None and not isinstance(variables, dict):
        raise HTTPException(status_code=400, detail="variables must be an object")
    pov = payload.get("pov")
    reset_queue = bool(payload.get("reset_queue"))
    status = MANAGER.set_mode(
        scene_id=scene_id,
        node_id=node_id,
        mode=mode,
        context=context,
        variables=variables,
        pov=_safe_text(pov) if pov else None,
        reset_queue=reset_queue,
    )
    return {"ok": True, "state": status}


@router.post("/api/narrator/propose")
async def narrator_propose(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_narrator", force=force)

    scene_id = _safe_text(payload.get("scene_id"))
    node_id = _safe_text(payload.get("node_id"))
    if not scene_id or not node_id:
        raise HTTPException(status_code=400, detail="scene_id and node_id are required")
    message = _safe_text(payload.get("prompt") or payload.get("message"))
    if not message:
        message = "Advance the story respecting player agency."
    context = payload.get("context")
    if context is not None and not isinstance(context, list):
        raise HTTPException(status_code=400, detail="context must be an array")
    choices = payload.get("choices")
    if choices is not None and not isinstance(choices, list):
        raise HTTPException(status_code=400, detail="choices must be an array")
    rationale = payload.get("rationale")
    role = _safe_text(payload.get("role") or DEFAULT_ROLE)
    status = MANAGER.propose(
        scene_id=scene_id,
        node_id=node_id,
        message=message,
        context=context,
        choices=choices,
        rationale=rationale,
        role=role,
    )
    return {"ok": True, "state": status}


@router.post("/api/narrator/apply")
async def narrator_apply(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_narrator", force=force)

    scene_id = _safe_text(payload.get("scene_id"))
    proposal_id = _safe_text(payload.get("proposal_id"))
    if not scene_id or not proposal_id:
        raise HTTPException(status_code=400, detail="scene_id and proposal_id required")
    status = MANAGER.apply(scene_id=scene_id, proposal_id=proposal_id)
    return {"ok": True, "state": status}


@router.post("/api/narrator/stop")
async def narrator_stop(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_narrator", force=force)
    scene_id = _safe_text(payload.get("scene_id"))
    if not scene_id:
        raise HTTPException(status_code=400, detail="scene_id required")
    status = MANAGER.stop(scene_id=scene_id)
    return {"ok": True, "state": status}


@router.post("/api/narrator/rollback")
async def narrator_rollback(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_narrator", force=force)

    scene_id = _safe_text(payload.get("scene_id"))
    if not scene_id:
        raise HTTPException(status_code=400, detail="scene_id required")
    steps = payload.get("steps", 1)
    try:
        steps_int = int(steps)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="steps must be an integer") from exc
    status = MANAGER.rollback(scene_id=scene_id, steps=steps_int)
    return {"ok": True, "state": status}


@router.post("/api/narrator/chat")
async def narrator_chat(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_narrator", force=force)

    scene_id = _safe_text(payload.get("scene_id") or "offline")
    node_id = _safe_text(payload.get("node_id") or "node")
    message = _safe_text(payload.get("message"))
    context = payload.get("context")
    if context is not None and not isinstance(context, list):
        raise HTTPException(status_code=400, detail="context must be an array")
    playback = ROLE_ORCHESTRATOR.route(
        role=payload.get("role") or DEFAULT_ROLE,
        message=message,
        context=context or [],
    )
    state = MANAGER.set_mode(
        scene_id=scene_id,
        node_id=node_id,
        mode="chat",
        context=context or [],
        pov=_safe_text(payload.get("pov")) if payload.get("pov") else None,
    )
    state["last_chat"] = {
        "reply": playback["reply"],
        "adapter": playback["adapter"],
        "model": playback["model"],
        "tokens": playback["tokens"],
        "budget": playback.get("budget"),
        "session": playback.get("session"),
    }
    return {"ok": True, "state": state}


@router.get("/api/llm/roles")
async def llm_roles(
    dry_run: bool = Query(False, description="Return routing dry-run plan"),
    role: Optional[str] = Query(None, description="Optional role filter"),
    message: str = Query(
        "Plan narrator turn", description="Sample message for dry-run"
    ),
) -> Dict[str, Any]:
    _require_enabled("enable_llm_role_mapping")
    snapshot = ROLE_ORCHESTRATOR.snapshot()
    plans: List[Dict[str, Any]] = []
    if dry_run:
        roles = [role] if role else [entry["role"] for entry in snapshot["roles"]]
        ctx: List[Dict[str, Any]] = [{"speaker": "System", "text": "Dry-run context"}]
        for role_name in roles:
            try:
                plan = ROLE_ORCHESTRATOR.plan(
                    role=role_name, message=message, context=ctx
                )
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Dry-run plan failed for %s: %s", role_name, exc)
                continue
            plans.append(plan)
    return {
        "ok": True,
        "roles": snapshot["roles"],
        "offline": snapshot["offline"],
        "plans": plans,
    }


@router.post("/api/llm/assign")
async def llm_assign(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    force = _bool(payload.get("force"))
    _require_enabled("enable_llm_role_mapping", force=force)
    role = _safe_text(payload.get("role"))
    if not role:
        raise HTTPException(status_code=400, detail="role is required")
    adapter = payload.get("adapter")
    model = payload.get("model")
    device = payload.get("device")
    budget_tokens = payload.get("budget_tokens")
    sticky = payload.get("sticky")
    metadata = (
        payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    )
    assignment = ROLE_ORCHESTRATOR.assign(
        role,
        adapter=adapter,
        model=model,
        device=device,
        budget_tokens=budget_tokens,
        sticky=sticky,
        metadata=metadata,
    )
    return {"ok": True, "assignment": assignment}


@router.get("/api/llm/health")
async def llm_health() -> Dict[str, Any]:
    _require_enabled("enable_llm_role_mapping")
    return ROLE_ORCHESTRATOR.health()


__all__ = ["router"]
