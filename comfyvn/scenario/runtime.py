from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, Field

from comfyvn.scenario.models import (
    ChoiceNode,
    ChoiceOptionSpec,
    ConditionSpec,
    EndNode,
    JumpNode,
    LineNode,
    ScenarioNode,
    ScenarioSpec,
    SetNode,
)


class ScenarioRuntimeError(RuntimeError):
    """Raised when the scenario runtime encounters an unrecoverable error."""


class ScenarioHistoryEntry(BaseModel):
    node_id: str
    kind: str
    choice_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class ScenarioStepEvent(BaseModel):
    type: str
    node_id: str
    data: Dict[str, Any] = Field(default_factory=dict)


class ScenarioState(BaseModel):
    node_id: Optional[str]
    variables: Dict[str, Any] = Field(default_factory=dict)
    history: List[ScenarioHistoryEntry] = Field(default_factory=list)
    steps: int = 0
    seed: str = "0"


class ScenarioStepResult(BaseModel):
    event: ScenarioStepEvent
    state: ScenarioState
    done: bool = False


def _hash_seed(material: str) -> int:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _normalize_seed(seed: Any) -> int:
    if isinstance(seed, int):
        return seed
    if isinstance(seed, str):
        try:
            return int(seed)
        except ValueError:
            return _hash_seed(seed)
    return 0


class ScenarioRuntime:
    def __init__(
        self,
        spec: ScenarioSpec | Dict[str, Any],
        *,
        seed: int | str | None = None,
        state: ScenarioState | Dict[str, Any] | None = None,
    ):
        if isinstance(spec, ScenarioSpec):
            self.spec = spec
        else:
            self.spec = ScenarioSpec.model_validate(spec)
        self._node_map: Dict[str, ScenarioNode] = {
            node.id: node for node in self.spec.nodes
        }
        if self.spec.start not in self._node_map:
            raise ScenarioRuntimeError(
                f"scenario start references missing node '{self.spec.start}'"
            )

        provided_seed = 0 if seed is None else seed
        self.seed = _normalize_seed(provided_seed)
        defaults = self._build_default_variables()
        if isinstance(state, ScenarioState):
            self.state = state
        elif isinstance(state, dict):
            self.state = ScenarioState.model_validate(state)
        else:
            self.state = ScenarioState(
                node_id=self.spec.start,
                variables=defaults,
                history=[],
                steps=0,
                seed=str(self.seed),
            )
        if self.state.variables is None:
            self.state.variables = {}
        for key, value in defaults.items():
            self.state.variables.setdefault(key, value)
        if self.state.node_id is None:
            self.state.node_id = self.spec.start
        if seed is None:
            if self.state.seed not in (None, ""):
                self.seed = _normalize_seed(self.state.seed)
            self.state.seed = str(self.seed)
        else:
            self.state.seed = str(self.seed)
        self._ensure_state_consistency()

    def _ensure_state_consistency(self) -> None:
        if self.state.node_id is not None and self.state.node_id not in self._node_map:
            raise ScenarioRuntimeError(
                f"state references unknown node '{self.state.node_id}'"
            )

    def _build_default_variables(self) -> Dict[str, Any]:
        return {
            name: spec.default for name, spec in (self.spec.variables or {}).items()
        }

    def _conditions_met(
        self, conditions: Sequence[ConditionSpec] | None, variables: Dict[str, Any]
    ) -> bool:
        if not conditions:
            return True
        return all(cond.evaluate(variables) for cond in conditions)

    def _deterministic_rng(self, node_id: str) -> random.Random:
        material = f"{self.seed}:{self.state.steps}:{node_id}"
        return random.Random(_hash_seed(material))

    def _available_choices(
        self, node: ChoiceNode, variables: Dict[str, Any]
    ) -> List[ChoiceOptionSpec]:
        return [
            option
            for option in node.choices
            if self._conditions_met(option.conditions, variables)
        ]

    def _pick_choice(
        self, node: ChoiceNode, options: Sequence[ChoiceOptionSpec]
    ) -> ChoiceOptionSpec:
        if not options:
            raise ScenarioRuntimeError(
                f"choice node '{node.id}' has no available options"
            )
        weighted = [opt for opt in options if opt.weight > 0]
        candidates = weighted or list(options)
        if len(candidates) == 1:
            return candidates[0]
        rng = self._deterministic_rng(node.id)
        total = sum(opt.weight for opt in candidates) if weighted else len(candidates)
        pick = rng.random() * total
        upto = 0.0
        for opt in candidates:
            step = opt.weight if weighted else 1.0
            upto += step
            if pick <= upto:
                return opt
        return candidates[-1]

    def _apply_assignment(self, assignments: Dict[str, Any]) -> Dict[str, Any]:
        if not assignments:
            return {}
        changed: Dict[str, Any] = {}
        for key, value in assignments.items():
            self.state.variables[key] = value
            changed[key] = value
        return changed

    def _record_history(
        self,
        node_id: str,
        kind: str,
        *,
        choice_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = ScenarioHistoryEntry(
            node_id=node_id,
            kind=kind,
            choice_id=choice_id,
            payload=payload or {},
        )
        self.state.history.append(entry)

    def _resolve_next(self, next_id: Optional[str]) -> Optional[str]:
        if next_id is None:
            return None
        if next_id not in self._node_map:
            raise ScenarioRuntimeError(f"node '{next_id}' does not exist")
        return next_id

    def finished(self) -> bool:
        return self.state.node_id is None

    def step(self, *, choice_id: Optional[str] = None) -> ScenarioStepResult:
        if self.state.node_id is None:
            raise ScenarioRuntimeError("scenario has already finished")
        node = self._node_map.get(self.state.node_id)
        if node is None:
            raise ScenarioRuntimeError(
                f"state references unknown node '{self.state.node_id}'"
            )

        if isinstance(node, LineNode):
            data = {
                "text": node.text,
                "speaker": node.speaker,
                "expression": node.expression,
                "tags": list(node.tags or []),
            }
            event = ScenarioStepEvent(type="line", node_id=node.id, data=data)
            next_id = self._resolve_next(node.next)
            self._record_history(node.id, "line", payload=data)
        elif isinstance(node, SetNode):
            changed = self._apply_assignment(node.assign)
            data = {"assign": changed}
            event = ScenarioStepEvent(type="set", node_id=node.id, data=data)
            next_id = self._resolve_next(node.next)
            self._record_history(node.id, "set", payload=data)
        elif isinstance(node, JumpNode):
            data = {"to": node.next}
            event = ScenarioStepEvent(type="jump", node_id=node.id, data=data)
            next_id = self._resolve_next(node.next)
            self._record_history(node.id, "jump", payload=data)
        elif isinstance(node, ChoiceNode):
            choices = self._available_choices(node, self.state.variables)
            selected: ChoiceOptionSpec
            if choice_id is not None:
                selected = next((opt for opt in choices if opt.id == choice_id), None)
                if selected is None:
                    raise ScenarioRuntimeError(
                        f"choice '{choice_id}' is not available for node '{node.id}'"
                    )
            else:
                selected = self._pick_choice(node, choices)
            changed = self._apply_assignment(selected.set)
            data = {
                "prompt": node.prompt,
                "choice": {
                    "id": selected.id,
                    "text": selected.text,
                },
                "changes": changed,
            }
            event = ScenarioStepEvent(type="choice", node_id=node.id, data=data)
            next_id = self._resolve_next(selected.next)
            self._record_history(
                node.id,
                "choice",
                choice_id=selected.id,
                payload=data,
            )
        elif isinstance(node, EndNode):
            data = {"result": node.result}
            event = ScenarioStepEvent(type="end", node_id=node.id, data=data)
            next_id = None
            self._record_history(node.id, "end", payload=data)
        else:  # pragma: no cover - defensive, union should cover all types
            raise ScenarioRuntimeError(f"unsupported node type '{type(node)!r}'")

        self.state.steps += 1
        self.state.node_id = next_id
        done = next_id is None
        snapshot = self.state.model_copy(deep=True)
        result = ScenarioStepResult(event=event, state=snapshot, done=done)
        if done:
            self.state.node_id = None
        return result

    def walk(self, limit: Optional[int] = None) -> Iterable[ScenarioStepResult]:
        steps = 0
        while not self.finished():
            if limit is not None and steps >= limit:
                break
            yield self.step()
            steps += 1
