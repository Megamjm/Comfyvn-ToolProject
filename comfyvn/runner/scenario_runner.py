from __future__ import annotations

import copy
import time
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)

try:  # Optional dependency wired through requirements.txt
    import jsonschema
except Exception:  # pragma: no cover - optional
    jsonschema = None

from comfyvn.core import modder_hooks
from comfyvn.schema import get_scenario_schema

from .rng import DeterministicRNG, RNGError

ValidationIssue = Dict[str, Any]

__all__ = ["ScenarioRunner", "validate_scene", "ValidationError"]

DEFAULT_POV = "narrator"


class ValidationError(Exception):
    """Raised when scene validation fails."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = list(issues)
        super().__init__("scene validation failed")


def _stringify_path(path: Iterable[Any]) -> str:
    parts: List[str] = []
    for token in path:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        elif not parts:
            parts.append(str(token))
        else:
            parts.append(f".{token}")
    out = "".join(parts)
    return out or "<root>"


def _unique_node_ids(
    nodes: Sequence[Mapping[str, Any]]
) -> Tuple[Dict[str, Mapping[str, Any]], List[ValidationIssue]]:
    seen: Dict[str, Mapping[str, Any]] = {}
    issues: List[ValidationIssue] = []
    for idx, node in enumerate(nodes):
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            issues.append(
                {
                    "path": f"nodes[{idx}].id",
                    "message": "node id must be a non-empty string",
                }
            )
            continue
        if node_id in seen:
            issues.append(
                {
                    "path": f"nodes[{idx}].id",
                    "message": f"duplicate node id '{node_id}'",
                }
            )
            continue
        seen[node_id] = node
    return seen, issues


def _validate_choice_targets(
    nodes_by_id: Mapping[str, Mapping[str, Any]]
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for node_id, node in nodes_by_id.items():
        raw_choices = node.get("choices")
        if not raw_choices:
            continue
        if not isinstance(raw_choices, list):
            issues.append(
                {
                    "path": f"nodes['{node_id}'].choices",
                    "message": "choices must be an array",
                }
            )
            continue
        for c_idx, choice in enumerate(raw_choices):
            target = choice.get("target")
            if not isinstance(target, str) or not target.strip():
                issues.append(
                    {
                        "path": f"nodes['{node_id}'].choices[{c_idx}].target",
                        "message": "choice target must be a node id",
                    }
                )
                continue
            if target not in nodes_by_id:
                issues.append(
                    {
                        "path": f"nodes['{node_id}'].choices[{c_idx}].target",
                        "message": f"choice target '{target}' not found",
                    }
                )
    return issues


def _build_jsonschema_validator():
    if not jsonschema:
        return None
    schema = get_scenario_schema()
    return jsonschema.Draft7Validator(schema)  # type: ignore[attr-defined]


_JSONSCHEMA_VALIDATOR = _build_jsonschema_validator()


def validate_scene(scene: Mapping[str, Any]) -> Tuple[bool, List[ValidationIssue]]:
    """
    Validate incoming scene using JSON Schema (if available) and bespoke topological checks.
    Returns (is_valid, issues).
    """
    issues: List[ValidationIssue] = []

    if not isinstance(scene, Mapping):
        return False, [{"path": "<root>", "message": "scene must be an object"}]

    if _JSONSCHEMA_VALIDATOR:
        for err in _JSONSCHEMA_VALIDATOR.iter_errors(scene):
            issues.append(
                {
                    "path": _stringify_path(err.path),
                    "message": err.message,
                }
            )

    nodes = scene.get("nodes", [])
    if not isinstance(nodes, list):
        issues.append({"path": "nodes", "message": "nodes must be an array"})
        nodes = []

    nodes_by_id, dup_issues = _unique_node_ids(nodes)
    issues.extend(dup_issues)

    start = scene.get("start")
    if not isinstance(start, str) or not start.strip():
        issues.append({"path": "start", "message": "start must be a node id"})
    elif nodes_by_id and start not in nodes_by_id:
        issues.append(
            {
                "path": "start",
                "message": f"start node '{start}' not present in nodes",
            }
        )

    issues.extend(_validate_choice_targets(nodes_by_id))

    return (len(issues) == 0), issues


def _split_key(key: str) -> List[str]:
    return [segment for segment in str(key).split(".") if segment]


def _resolve_path(data: Mapping[str, Any], key: str) -> Tuple[bool, Any]:
    segments = _split_key(key)
    current: Any = data
    for segment in segments:
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        else:
            return False, None
    return True, current


def _ensure_parent(
    container: MutableMapping[str, Any], segments: Sequence[str]
) -> MutableMapping[str, Any]:
    current: MutableMapping[str, Any] = container
    for segment in segments[:-1]:
        node = current.get(segment)
        if not isinstance(node, MutableMapping):
            node = {}
            current[segment] = node
        current = node  # type: ignore[assignment]
    return current


def _apply_action(
    action: Mapping[str, Any], variables: MutableMapping[str, Any]
) -> None:
    action_type = action.get("type")
    raw_key = action.get("key")
    if not isinstance(action_type, str) or not isinstance(raw_key, str):
        return

    segments = _split_key(raw_key)
    if not segments:
        return

    parent = _ensure_parent(variables, segments)
    leaf = segments[-1]

    if action_type == "set":
        parent[leaf] = action.get("value")
        return

    if action_type in {"increment", "decrement"}:
        amount = action.get("amount")
        if amount is None:
            amount = action.get("value", 1)
        try:
            delta = float(amount)
        except Exception:
            delta = 1.0
        exists, current_val = _resolve_path(variables, raw_key)
        base = (
            float(current_val)
            if exists and isinstance(current_val, (int, float))
            else 0.0
        )
        if action_type == "decrement":
            delta *= -1
        parent[leaf] = base + delta
        return

    if action_type == "clear":
        if leaf in parent:
            del parent[leaf]
        return


def _apply_actions(
    actions: Optional[Sequence[Mapping[str, Any]]],
    variables: MutableMapping[str, Any],
) -> None:
    if not actions:
        return
    for action in actions:
        if isinstance(action, Mapping):
            _apply_action(action, variables)


def _check_condition(
    condition: Mapping[str, Any],
    variables: Mapping[str, Any],
) -> bool:
    key = condition.get("key")
    operator = condition.get("operator")
    if not isinstance(key, str) or not isinstance(operator, str):
        return False

    exists, current = _resolve_path(variables, key)
    value = condition.get("value")

    if operator == "exists":
        return exists
    if operator == "not_exists":
        return not exists
    if not exists:
        return False

    if operator == "eq":
        return current == value
    if operator == "neq":
        return current != value
    if operator == "gt":
        try:
            return float(current) > float(value)
        except Exception:
            return False
    if operator == "gte":
        try:
            return float(current) >= float(value)
        except Exception:
            return False
    if operator == "lt":
        try:
            return float(current) < float(value)
        except Exception:
            return False
    if operator == "lte":
        try:
            return float(current) <= float(value)
        except Exception:
            return False
    if operator == "in":
        if isinstance(value, Sequence):
            return current in value
        return False
    if operator == "not_in":
        if isinstance(value, Sequence):
            return current not in value
        return False
    return False


def _normalise_visible_to(raw: Any) -> List[str]:
    if isinstance(raw, str):
        candidate = raw.strip()
        return [candidate] if candidate else []
    if isinstance(raw, Iterable):
        values: List[str] = []
        for item in raw:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate:
                    values.append(candidate)
        return values
    return []


def _available_choices(
    node: Mapping[str, Any],
    variables: Mapping[str, Any],
    *,
    pov: Optional[str],
) -> List[Mapping[str, Any]]:
    raw = node.get("choices") or []
    if not isinstance(raw, list):
        return []
    filtered: List[Mapping[str, Any]] = []
    for choice in raw:
        if not isinstance(choice, Mapping):
            continue
        visible_to = _normalise_visible_to(choice.get("visible_to"))
        if visible_to and (pov is None or str(pov) not in visible_to):
            continue
        weight = choice.get("weight", 1)
        try:
            weight_value = float(weight)
        except Exception:
            weight_value = 0.0
        if weight_value <= 0:
            continue
        conditions = choice.get("conditions") or []
        if isinstance(conditions, list) and all(
            _check_condition(cond, variables)
            for cond in conditions
            if isinstance(cond, Mapping)
        ):
            filtered.append(choice)
        elif not conditions:
            filtered.append(choice)
    return filtered


class ScenarioRunner:
    """
    Deterministic scene runner that advances a state payload one node at a time.
    """

    def __init__(self, scene: Mapping[str, Any]):
        ok, issues = validate_scene(scene)
        if not ok:
            raise ValidationError(issues)

        self._scene = copy.deepcopy(scene)
        self._scene_id = str(scene.get("id") or "scene")
        self._start_node_id = str(scene["start"])

        nodes = scene.get("nodes") or []
        self._nodes: Dict[str, Mapping[str, Any]] = {}
        for node in nodes:
            node_id = str(node["id"])
            self._nodes[node_id] = copy.deepcopy(node)

        raw_vars = scene.get("variables") or {}
        self._default_variables: Dict[str, Any] = (
            copy.deepcopy(raw_vars) if isinstance(raw_vars, Mapping) else {}
        )
        self._default_pov_id = self._coalesce_default_pov(scene)

    @property
    def scene_id(self) -> str:
        return self._scene_id

    @property
    def start_node(self) -> str:
        return self._start_node_id

    def _node(self, node_id: str) -> Mapping[str, Any]:
        return self._nodes[node_id]

    def _clone_node(self, node_id: str) -> Dict[str, Any]:
        return copy.deepcopy(self._nodes[node_id])

    def _coalesce_default_pov(self, scene: Mapping[str, Any]) -> str:
        raw = scene.get("default_pov")
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                return candidate
        metadata = scene.get("metadata")
        if isinstance(metadata, Mapping):
            meta_default = metadata.get("default_pov")
            if isinstance(meta_default, str):
                candidate = meta_default.strip()
                if candidate:
                    return candidate
        return DEFAULT_POV

    def _normalize_pov_value(self, pov: Any) -> str:
        if isinstance(pov, str):
            candidate = pov.strip()
            if candidate:
                return candidate
        return self._default_pov_id

    def initial_state(
        self,
        *,
        seed: Optional[int] = None,
        variables: Optional[Mapping[str, Any]] = None,
        pov: Optional[str] = None,
    ) -> Dict[str, Any]:
        merged_vars = copy.deepcopy(self._default_variables)
        if variables:
            for key, value in variables.items():
                merged_vars[key] = copy.deepcopy(value)

        rng_seed = int(seed if seed is not None else 0)
        rng = DeterministicRNG.from_seed(rng_seed)

        resolved_pov = self._normalize_pov_value(pov)

        state = {
            "scene_id": self.scene_id,
            "current_node": self.start_node,
            "variables": merged_vars,
            "history": [{"node": self.start_node, "choice": None}],
            "rng": rng.to_state(),
            "finished": False,
            "pov": resolved_pov,
        }

        start_node = self._node(self.start_node)
        _apply_actions(start_node.get("actions"), state["variables"])
        available_start = _available_choices(
            start_node, state["variables"], pov=resolved_pov
        )
        if not available_start:
            state["finished"] = True
        timestamp = time.time()
        try:
            modder_hooks.emit(
                "on_scene_enter",
                {
                    "scene_id": self.scene_id,
                    "node": self.start_node,
                    "pov": resolved_pov,
                    "variables": copy.deepcopy(state["variables"]),
                    "history": list(state.get("history", [])),
                    "finished": state["finished"],
                    "timestamp": timestamp,
                },
            )
            modder_hooks.emit(
                "on_choice_render",
                {
                    "scene_id": self.scene_id,
                    "node": self.start_node,
                    "choices": copy.deepcopy(available_start),
                    "pov": resolved_pov,
                    "finished": state["finished"],
                    "timestamp": timestamp,
                },
            )
        except Exception:
            pass
        return state

    def peek(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        current_id = str(state.get("current_node") or self.start_node)
        node = self._clone_node(current_id)
        variables = state.get("variables")
        if not isinstance(variables, Mapping):
            variables = {}
        pov_value = self._normalize_pov_value(state.get("pov"))
        choices = [
            copy.deepcopy(choice)
            for choice in _available_choices(node, variables, pov=pov_value)
        ]
        finished = bool(state.get("finished")) or not choices
        return {
            "node": node,
            "choices": choices,
            "finished": finished,
        }

    def _ensure_rng(
        self, state: MutableMapping[str, Any], seed: Optional[int]
    ) -> DeterministicRNG:
        rng_state = state.get("rng")
        if isinstance(rng_state, MutableMapping):
            return DeterministicRNG.from_state(rng_state)
        if seed is None:
            seed = 0
        rng = DeterministicRNG.from_seed(int(seed))
        state["rng"] = rng.to_state()
        return rng

    def step(
        self,
        state: Mapping[str, Any],
        *,
        choice_id: Optional[str] = None,
        seed: Optional[int] = None,
        pov: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(state, Mapping):
            raise ValueError("state must be a mapping")

        working: Dict[str, Any] = copy.deepcopy(state)
        scene_marker = working.get("scene_id")
        if scene_marker not in {self.scene_id, None}:
            raise ValueError("state.scene_id does not match runner scene")
        working["scene_id"] = self.scene_id

        current_node_id = str(working.get("current_node") or self.start_node)
        if current_node_id not in self._nodes:
            raise ValueError(f"unknown node '{current_node_id}'")

        if working.get("finished"):
            return working

        variables = working.get("variables")
        if not isinstance(variables, MutableMapping):
            variables = {}
            working["variables"] = variables

        if pov is not None:
            working["pov"] = pov
        current_pov = self._normalize_pov_value(working.get("pov"))
        working["pov"] = current_pov

        node = self._node(current_node_id)
        available = _available_choices(node, variables, pov=current_pov)

        if not available:
            working["finished"] = True
            return working

        choice = None
        if choice_id:
            for candidate in available:
                candidate_id = candidate.get("id") or candidate.get("target")
                if candidate_id == choice_id:
                    choice = candidate
                    break
            if choice is None:
                raise ValueError(f"choice '{choice_id}' is not available")
            rng = self._ensure_rng(working, seed)
            working["rng"] = rng.to_state()
        else:
            rng = self._ensure_rng(working, seed)
            try:
                idx = rng.weighted_index([float(c.get("weight", 1)) for c in available])
            except RNGError as exc:
                raise ValueError(str(exc)) from exc
            choice = available[idx]
            working["rng"] = rng.to_state()

        _apply_actions(choice.get("actions"), variables)

        target = str(choice.get("target"))
        if target not in self._nodes:
            raise ValueError(f"choice target '{target}' missing from scene")

        history = working.setdefault("history", [])
        if isinstance(history, list):
            history.append(
                {
                    "node": current_node_id,
                    "choice": choice.get("id") or choice.get("target"),
                }
            )

        working["current_node"] = target

        next_node = self._node(target)
        _apply_actions(next_node.get("actions"), variables)

        available_next = _available_choices(next_node, variables, pov=current_pov)
        working["finished"] = not available_next
        return working
