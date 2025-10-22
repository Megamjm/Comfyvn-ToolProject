from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from comfyvn.dungeon.backends import DoomLiteBackend, GridBackend

try:
    from comfyvn.core import modder_hooks
except Exception:  # pragma: no cover - optional import for headless utilities
    modder_hooks = None  # type: ignore

LOGGER = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600
SNAPSHOT_TOOL_ID = "comfyvn.dungeon.snapshot"


def _register_modder_hooks() -> None:
    if modder_hooks is None:
        return
    spec_map = modder_hooks.HOOK_SPECS
    if "on_dungeon_enter" not in spec_map:
        spec_map["on_dungeon_enter"] = modder_hooks.HookSpec(
            name="on_dungeon_enter",
            description="Emitted when a dungeon session is created and the first room is resolved.",
            payload_fields={
                "session_id": "Deterministic session identifier.",
                "backend": "Backend key (grid|doomlite).",
                "seed": "Seed used for deterministic generation.",
                "room_state": "Initial room payload including desc/exits/hazards/loot.",
                "anchors": "Event anchors mapping for the session and room.",
                "context": "Optional VN context (scene/node/worldline/pov/vars).",
            },
            ws_topic="modder.on_dungeon_enter",
            rest_event="on_dungeon_enter",
        )
    if "on_dungeon_leave" not in spec_map:
        spec_map["on_dungeon_leave"] = modder_hooks.HookSpec(
            name="on_dungeon_leave",
            description="Dispatched when a dungeon session finalises and returns a VN snapshot payload.",
            payload_fields={
                "session_id": "Session identifier that completed.",
                "backend": "Backend key (grid|doomlite).",
                "seed": "Seed used for deterministic generation.",
                "summary": "Final backend summary (rooms explored, hazards resolved, loot).",
                "vn_snapshot": "Snapshot payload suitable for Snapshot→Node/Fork.",
                "context": "VN context (scene/node/worldline/pov/vars).",
            },
            ws_topic="modder.on_dungeon_leave",
            rest_event="on_dungeon_leave",
        )
    if "on_dungeon_snapshot" not in spec_map:
        spec_map["on_dungeon_snapshot"] = modder_hooks.HookSpec(
            name="on_dungeon_snapshot",
            description="Published whenever the dungeon runtime records a snapshot payload.",
            payload_fields={
                "session_id": "Session identifier that produced the snapshot.",
                "backend": "Backend key (grid|doomlite).",
                "reason": "Reason for capture (enter|step|resolve|leave|manual).",
                "anchor": "Current room anchor when captured.",
                "snapshot": "Snapshot payload emitted by the backend.",
                "anchors": "Session anchor mapping for consumers.",
                "context": "VN context forwarded from the caller.",
            },
            ws_topic="modder.on_dungeon_snapshot",
            rest_event="on_dungeon_snapshot",
        )


_register_modder_hooks()


class DungeonAPIError(RuntimeError):
    """Raised when the dungeon API receives invalid input or state."""


class DungeonSessionNotFound(DungeonAPIError):
    """Raised when a provided session identifier is unknown."""


@dataclass
class DungeonSession:
    session_id: str
    backend_name: str
    backend: Any
    seed: int
    rng: random.Random
    state: MutableMapping[str, Any]
    room_state: Mapping[str, Any]
    context: Dict[str, Any]
    anchors: Dict[str, Any]
    path: list[Dict[str, Any]] = field(default_factory=list)
    encounters: list[Dict[str, Any]] = field(default_factory=list)
    snapshots: list[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


class DungeonAPI:
    """In-memory orchestrator for dungeon sessions."""

    def __init__(self, *, session_ttl: float = SESSION_TTL_SECONDS) -> None:
        self._session_ttl = session_ttl
        grid_backend = GridBackend()
        doom_backend = DoomLiteBackend()
        self._backends: Dict[str, Tuple[str, Any]] = {
            "grid": ("grid", grid_backend),
            "gridcrawler": ("grid", grid_backend),
            "grid_crawler": ("grid", grid_backend),
            "doomlite": ("doomlite", doom_backend),
            "doom": ("doomlite", doom_backend),
            "stage": ("doomlite", doom_backend),
        }
        self._sessions: Dict[str, DungeonSession] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------ public API
    def enter(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._ensure_mapping(payload, detail="payload must be an object")
        backend_key = str(data.get("backend") or data.get("mode") or "grid").lower()
        backend_info = self._backends.get(backend_key)
        if not backend_info:
            raise DungeonAPIError(f"Unsupported backend '{backend_key}'")
        backend_name, backend = backend_info

        seed = self._coerce_seed(data.get("seed"))
        options = self._ensure_mapping(data.get("options"), default={})
        context = self._extract_context(data)

        session_id = self._coerce_session_id(data.get("session_id"))
        with self._lock:
            self._clean_expired_locked()
            if session_id and session_id in self._sessions:
                raise DungeonAPIError(f"Session '{session_id}' already active")
            if not session_id:
                session_id = self._make_session_id(backend_name, seed)
            rng = random.Random(seed)
            state, room_state = backend.enter(
                seed=seed, options=options, rng=rng, context=context
            )
            anchors = self._build_anchors(session_id, backend_name, room_state, context)
            path_entry = self._path_entry(room_state)
            session = DungeonSession(
                session_id=session_id,
                backend_name=backend_name,
                backend=backend,
                seed=seed,
                rng=rng,
                state=state,
                room_state=room_state,
                context=context,
                anchors=anchors,
                path=[path_entry],
            )
            self._sessions[session_id] = session
            session.touch()

        snapshot = self._capture_snapshot(session, reason="enter", store=False)
        self._emit_hook(
            "on_dungeon_enter",
            {
                "session_id": session.session_id,
                "backend": session.backend_name,
                "seed": session.seed,
                "room_state": session.room_state,
                "anchors": dict(session.anchors),
                "context": dict(session.context),
            },
        )

        response = {
            "session_id": session.session_id,
            "backend": session.backend_name,
            "seed": session.seed,
            "room_state": session.room_state,
            "anchors": dict(session.anchors),
            "snapshot_hooks": self._snapshot_hooks_payload(),
            "determinism": self._determinism_payload(session),
            "context": dict(session.context),
        }
        if snapshot:
            response["snapshot"] = snapshot
        return response

    def step(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._ensure_mapping(payload, detail="payload must be an object")
        session = self._get_session(data.get("session_id"))
        direction = str(
            data.get("direction") or data.get("move") or data.get("step") or ""
        ).strip()
        if not direction:
            raise DungeonAPIError("direction is required for step")
        collect = data.get("collect_loot") or ()
        collect_ids: Iterable[str] = ()
        if isinstance(collect, (list, tuple, set)):
            collect_ids = [str(entry) for entry in collect]

        with self._lock:
            state, room, movement = session.backend.step(
                session.state, direction=direction, rng=session.rng
            )
            session.state = state
            session.room_state = room
            session.anchors["room"] = room.get("anchor")
            session.path.append(self._path_entry(room))
            collected = []
            if collect_ids:
                collected = session.backend.collect_loot(session.state, collect_ids)
            session.touch()

        snapshot = None
        if data.get("snapshot"):
            snapshot = self._capture_snapshot(session, reason="step")
        response = {
            "session_id": session.session_id,
            "backend": session.backend_name,
            "room_state": session.room_state,
            "movement": movement,
            "anchors": dict(session.anchors),
            "determinism": self._determinism_payload(session),
            "encounter_available": any(
                hazard.get("status") == "active"
                for hazard in session.room_state.get("hazards", [])
            ),
        }
        if collected:
            response["loot_collected"] = collected
        if snapshot:
            response["snapshot"] = snapshot
        return response

    def encounter_start(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._ensure_mapping(payload, detail="payload must be an object")
        session = self._get_session(data.get("session_id"))
        hazard_id = data.get("hazard_id")
        hazard_ref = str(hazard_id).strip() if hazard_id else None

        with self._lock:
            encounter = session.backend.encounter_start(
                session.state, hazard_id=hazard_ref, rng=session.rng
            )
            entry = {
                "id": encounter["id"],
                "anchor": encounter.get("anchor"),
                "room_anchor": session.room_state.get("anchor"),
                "started_at": time.time(),
                "outcome": None,
            }
            session.encounters.append(entry)
            session.anchors["encounter"] = encounter.get("anchor")
            session.touch()

        if data.get("snapshot"):
            snapshot = self._capture_snapshot(session, reason="encounter_start")
        else:
            snapshot = None
        response = {
            "session_id": session.session_id,
            "backend": session.backend_name,
            "encounter": encounter,
            "anchors": dict(session.anchors),
            "room_state": session.room_state,
            "determinism": self._determinism_payload(session),
        }
        if snapshot:
            response["snapshot"] = snapshot
        return response

    def resolve(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._ensure_mapping(payload, detail="payload must be an object")
        session = self._get_session(data.get("session_id"))
        outcome = self._ensure_mapping(
            data.get("outcome") or data.get("result"),
            detail="outcome must be an object",
        )

        with self._lock:
            summary, loot, room = session.backend.resolve(
                session.state, outcome=outcome, rng=session.rng
            )
            session.state = session.state
            session.room_state = room
            session.anchors["room"] = room.get("anchor")
            for entry in reversed(session.encounters):
                if (
                    entry["id"] == summary["encounter_id"]
                    and entry.get("outcome") is None
                ):
                    entry["outcome"] = summary["outcome"]
                    entry["completed_at"] = time.time()
                    break
            session.touch()

        snapshot = None
        if data.get("snapshot"):
            snapshot = self._capture_snapshot(session, reason="resolve")
        response = {
            "session_id": session.session_id,
            "backend": session.backend_name,
            "encounter_outcome": summary,
            "loot": loot,
            "room_state": session.room_state,
            "anchors": dict(session.anchors),
            "determinism": self._determinism_payload(session),
        }
        if snapshot:
            response["snapshot"] = snapshot
        return response

    def leave(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._ensure_mapping(payload, detail="payload must be an object")
        session = self._get_session(data.get("session_id"))
        with self._lock:
            summary = session.backend.finalize(session.state)
            snapshot = self._capture_snapshot(session, reason="leave")
            vn_snapshot = self._build_vn_snapshot(session, summary, snapshot)
            response = {
                "session_id": session.session_id,
                "backend": session.backend_name,
                "seed": session.seed,
                "summary": summary,
                "vn_snapshot": vn_snapshot,
                "anchors": dict(session.anchors),
                "determinism": self._determinism_payload(session),
            }
            self._emit_hook(
                "on_dungeon_leave",
                {
                    "session_id": session.session_id,
                    "backend": session.backend_name,
                    "seed": session.seed,
                    "summary": summary,
                    "vn_snapshot": vn_snapshot,
                    "context": dict(session.context),
                },
            )
            del self._sessions[session.session_id]
        response["snapshot"] = snapshot
        return response

    # ------------------------------------------------------------------ helpers
    def _get_session(self, session_id: Any) -> DungeonSession:
        session_key = self._coerce_session_id(session_id)
        if not session_key:
            raise DungeonAPIError("session_id is required")
        with self._lock:
            self._clean_expired_locked()
            session = self._sessions.get(session_key)
        if not session:
            raise DungeonSessionNotFound(f"Unknown session '{session_key}'")
        return session

    def _capture_snapshot(
        self,
        session: DungeonSession,
        *,
        reason: str,
        store: bool = True,
    ) -> Dict[str, Any]:
        snapshot = session.backend.snapshot(
            session.state, context=session.context, path=session.path
        )
        payload = {
            "session_id": session.session_id,
            "backend": session.backend_name,
            "reason": reason,
            "anchor": session.room_state.get("anchor"),
            "snapshot": snapshot,
            "anchors": dict(session.anchors),
            "context": dict(session.context),
        }
        if store:
            entry = dict(payload)
            entry["captured_at"] = time.time()
            session.snapshots.append(entry)
        self._emit_hook("on_dungeon_snapshot", payload)
        return snapshot

    def _build_vn_snapshot(
        self,
        session: DungeonSession,
        summary: Mapping[str, Any],
        snapshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "tool": SNAPSHOT_TOOL_ID,
            "version": "v1",
            "backend": session.backend_name,
            "seed": session.seed,
            "anchors": dict(session.anchors),
            "context": dict(session.context),
            "path": list(session.path),
            "encounters": list(session.encounters),
            "summary": dict(summary),
            "payload": dict(snapshot),
        }

    def _clean_expired_locked(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.updated_at > self._session_ttl
        ]
        for session_id in expired:
            LOGGER.debug("Expiring dungeon session %s", session_id)
            self._sessions.pop(session_id, None)

    def _coerce_seed(self, value: Any) -> int:
        if value is None:
            return random.SystemRandom().randrange(1, 2**31 - 1)
        try:
            seed = int(value)
        except Exception as exc:
            raise DungeonAPIError("seed must be an integer") from exc
        if seed <= 0:
            raise DungeonAPIError("seed must be a positive integer")
        return seed

    def _coerce_session_id(self, value: Any) -> str:
        if not value:
            return ""
        text = str(value).strip()
        return text

    def _make_session_id(self, backend: str, seed: int) -> str:
        return f"{backend}-{seed}-{uuid.uuid4().hex[:8]}"

    def _extract_context(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        for key in ("scene", "scene_id"):
            if key in payload and isinstance(payload[key], str):
                context["scene"] = payload[key]
                break
        for key in ("node", "node_id"):
            if key in payload and isinstance(payload[key], str):
                context["node"] = payload[key]
                break
        pov = payload.get("pov")
        if isinstance(pov, str) and pov.strip():
            context["pov"] = pov.strip()
        worldline = payload.get("worldline")
        if isinstance(worldline, str) and worldline.strip():
            context["worldline"] = worldline.strip()
        vars_payload = payload.get("vars")
        if isinstance(vars_payload, Mapping):
            context["vars"] = dict(vars_payload)
        return context

    def _build_anchors(
        self,
        session_id: str,
        backend_name: str,
        room_state: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Dict[str, Any]:
        anchors = {
            "session": f"dungeon://{session_id}",
            "backend": backend_name,
            "room": room_state.get("anchor"),
        }
        if context.get("scene"):
            anchors["scene"] = context["scene"]
        if context.get("node"):
            anchors["node"] = context["node"]
        if context.get("worldline"):
            anchors["worldline"] = context["worldline"]
        if context.get("pov"):
            anchors["pov"] = context["pov"]
        return anchors

    def _path_entry(self, room_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "anchor": room_state.get("anchor"),
            "coords": room_state.get("coords"),
            "entered_at": time.time(),
        }

    def _determinism_payload(self, session: DungeonSession) -> Dict[str, Any]:
        return {
            "seed": session.seed,
            "backend": session.backend_name,
            "steps": max(0, len(session.path) - 1),
            "encounters": len(session.encounters),
        }

    def _snapshot_hooks_payload(self) -> list[Dict[str, Any]]:
        return [
            {
                "hook": "on_dungeon_enter",
                "payload": [
                    "session_id",
                    "backend",
                    "seed",
                    "room_state",
                    "anchors",
                    "context",
                ],
            },
            {
                "hook": "on_dungeon_snapshot",
                "payload": [
                    "session_id",
                    "backend",
                    "anchor",
                    "reason",
                    "snapshot",
                    "anchors",
                ],
            },
            {
                "hook": "on_dungeon_leave",
                "payload": [
                    "session_id",
                    "backend",
                    "seed",
                    "summary",
                    "vn_snapshot",
                    "context",
                ],
            },
        ]

    def _ensure_mapping(
        self,
        value: Any,
        *,
        detail: str = "value must be an object",
        default: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        if value is None and default is not None:
            return default
        if isinstance(value, Mapping):
            return value
        raise DungeonAPIError(detail)

    def _emit_hook(self, name: str, payload: Mapping[str, Any]) -> None:
        if modder_hooks is None:
            return
        try:
            modder_hooks.emit(name, dict(payload))
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.warning("Modder hook %s failed", name, exc_info=True)


API = DungeonAPI()
