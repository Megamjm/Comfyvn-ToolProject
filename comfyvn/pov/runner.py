from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import RLock
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
)

from .manager import POV, POVManager

LOGGER = logging.getLogger(__name__)

FilterFunction = Callable[[Mapping[str, Any], Mapping[str, Any]], bool]


@dataclass(slots=True)
class POVRunnerTraceStep:
    """Trace entry describing how a filter evaluated a candidate."""

    name: str
    decision: str
    error: Optional[str] = None


class POVRunner:
    """
    Lightweight orchestration layer for POV-aware scene handling.

    The runner extends :class:`POVManager` with filter hooks, debug traces, and
    helper utilities that future render/LoRA integrations can extend.
    """

    def __init__(self, manager: POVManager | None = None) -> None:
        self._manager = manager or POVManager()
        self._filters: Dict[str, FilterFunction] = {}
        self._lock = RLock()

    # ---------------------------------------------------------------- manager
    @property
    def manager(self) -> POVManager:
        return self._manager

    def attach_manager(self, manager: POVManager) -> None:
        if not isinstance(manager, POVManager):
            raise TypeError("manager must be an instance of POVManager")
        with self._lock:
            self._manager = manager

    def current_context(self) -> Dict[str, Any]:
        """Return a predictable payload for debug feeds and adapters."""
        snapshot = self._manager.snapshot()
        with self._lock:
            filter_names = list(self._filters.keys())
        world_payload = None
        try:
            from .worldlines import WORLDLINES  # avoid import cycles at module load
        except Exception:  # pragma: no cover - optional
            world_payload = None
        else:
            world_payload = WORLDLINES.active_snapshot()
        return {
            "pov": snapshot.get("pov"),
            "history": list(snapshot.get("history", [])),
            "filters": filter_names,
            "world": world_payload,
        }

    # ---------------------------------------------------------------- filters
    def register_filter(self, name: str, func: FilterFunction) -> None:
        """
        Register a filter callback.

        Filters receive ``(candidate, context)`` where ``candidate`` is a mapping
        with ``id``/``name`` keys and ``context`` exposes ``scene`` and the
        manager snapshot. Returning ``False`` drops the candidate from the final
        list; returning ``True`` keeps evaluation going.
        """

        if not callable(func):
            raise TypeError("func must be callable")
        key = name.strip()
        if not key:
            raise ValueError("filter name must be a non-empty string")
        with self._lock:
            self._filters[key] = func

    def unregister_filter(self, name: str) -> None:
        with self._lock:
            self._filters.pop(name, None)

    def list_filters(self) -> List[str]:
        with self._lock:
            return list(self._filters.keys())

    # ---------------------------------------------------------------- helpers
    def candidates(
        self,
        scene: Mapping[str, Any],
        *,
        with_trace: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]] | List[Dict[str, Any]]:
        """
        Return POV candidates for a scene.

        When ``with_trace`` is ``True`` the second element of the returned tuple
        contains filter trace entries for debugging.
        """

        raw = self._manager.candidates(scene)
        if not raw:
            if with_trace:
                return [], []
            return []

        kept: List[Dict[str, Any]] = []
        trace_payload: List[Dict[str, Any]] = []
        context = {
            "scene": scene,
            "snapshot": self._manager.snapshot(),
        }
        filters = self._snapshot_filters()

        for candidate in raw:
            keep, trace_steps = self._apply_filters(candidate, context, filters)
            if keep:
                kept.append(candidate)
            if with_trace:
                trace_payload.append(
                    {
                        "candidate": candidate,
                        "trace": [
                            {
                                "name": step.name,
                                "decision": step.decision,
                                "error": step.error,
                            }
                            for step in trace_steps
                        ],
                    }
                )

        if with_trace:
            return kept, trace_payload
        return kept

    def ensure_render_assets(
        self,
        scene: Mapping[str, Any],
        *,
        auto_create: bool = False,
    ) -> Dict[str, Any]:
        """
        Placeholder hook — verify render assets exist for the provided scene.

        Once Phase 6B lands this will talk to the render registry/LoRA cache.
        """

        candidates = self._manager.candidates(scene)
        return {
            "ok": True,
            "checked": len(candidates),
            "auto_created": auto_create,
            "missing": [],
        }

    # -------------------------------------------------------------- internals
    def _snapshot_filters(self) -> List[tuple[str, FilterFunction]]:
        with self._lock:
            return list(self._filters.items())

    def _apply_filters(
        self,
        candidate: Mapping[str, Any],
        context: Mapping[str, Any],
        filters: Iterable[tuple[str, FilterFunction]],
    ) -> tuple[bool, List[POVRunnerTraceStep]]:
        steps: List[POVRunnerTraceStep] = []
        keep = True
        for name, func in filters:
            decision = "keep"
            error_msg: Optional[str] = None
            try:
                keep_candidate = bool(func(candidate, context))
            except Exception as exc:  # pragma: no cover - defensive
                keep_candidate = True
                decision = "error"
                error_msg = str(exc)
                LOGGER.debug("POV filter %s raised error: %s", name, exc)
            if not keep_candidate:
                keep = False
                decision = "drop"
            steps.append(
                POVRunnerTraceStep(name=name, decision=decision, error=error_msg)
            )
            if not keep_candidate:
                break
        return keep, steps


# Shared singleton matching the manager singleton to simplify imports
POV_RUNNER = POVRunner(POV)

__all__ = ["POVRunner", "POVRunnerTraceStep", "POV_RUNNER"]
