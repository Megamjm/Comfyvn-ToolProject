from __future__ import annotations

"""
Scene/worldline diff helpers used by the diff-merge API surface.
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from comfyvn.pov.timeline_worlds import diff_worlds
from comfyvn.pov.worldlines import WORLDLINES, Worldline, WorldlineRegistry

__all__ = ["diff_worldline_scenes"]


@dataclass(slots=True, frozen=True)
class _ScenarioNode:
    node_id: str
    label: str | None
    node_type: str | None
    summary: Dict[str, Any]


def _resolve_worldline(
    candidate: str | Worldline,
    registry: WorldlineRegistry,
) -> Worldline:
    if isinstance(candidate, Worldline):
        return candidate
    return registry.ensure(candidate)


def _filter_choices(world: Worldline, mask_by_pov: bool) -> Dict[str, Dict[str, Any]]:
    raw = world.choice_map()
    if not mask_by_pov:
        return {pov: dict(entries) for pov, entries in raw.items()}
    pov_key = (world.pov or "").strip()
    if not pov_key:
        return {}
    payload = raw.get(pov_key) or {}
    return {pov_key: dict(payload)}


def _order_nodes(world: Worldline) -> list[str]:
    metadata = world.metadata or {}
    timeline = metadata.get("timeline")
    if isinstance(timeline, Mapping):
        order = timeline.get("order") or timeline.get("nodes")
        if isinstance(order, Sequence):
            ordered: list[str] = []
            for entry in order:
                text = str(entry or "").strip()
                if text:
                    ordered.append(text)
            if ordered:
                return ordered
    nodes = world.branch_nodes()
    return list(nodes)


def _scenario_lookup(scenario: Any) -> Dict[str, _ScenarioNode]:
    if scenario is None:
        return {}

    def _normalise_entry(entry: Any) -> Optional[_ScenarioNode]:
        node_id: Optional[str] = None
        label: Optional[str] = None
        node_type: Optional[str] = None
        summary: Dict[str, Any] = {}

        if hasattr(entry, "id"):
            node_id = str(getattr(entry, "id"))
            label = getattr(entry, "label", None)
            node_type = getattr(entry, "type", None)
            if hasattr(entry, "text"):
                summary["text"] = getattr(entry, "text")[:80]
            if hasattr(entry, "prompt"):
                summary["prompt"] = getattr(entry, "prompt")[:80]
            if hasattr(entry, "speaker"):
                summary["speaker"] = getattr(entry, "speaker")
            if hasattr(entry, "choices"):
                try:
                    choices = list(getattr(entry, "choices"))
                except TypeError:
                    choices = []
                summary["choices"] = len(choices)
            if hasattr(entry, "next"):
                summary["next"] = getattr(entry, "next")
        elif isinstance(entry, Mapping):
            raw_id = entry.get("id")
            if isinstance(raw_id, str):
                node_id = raw_id
            elif raw_id is not None:
                node_id = str(raw_id)
            label_value = entry.get("label")
            if label_value is not None:
                label = str(label_value)
            type_value = entry.get("type")
            if type_value is not None:
                node_type = str(type_value)
            if entry.get("text"):
                summary["text"] = str(entry["text"])[:80]
            if entry.get("prompt"):
                summary["prompt"] = str(entry["prompt"])[:80]
            if entry.get("speaker"):
                summary["speaker"] = str(entry["speaker"])
            if "choices" in entry and isinstance(entry["choices"], Sequence):
                summary["choices"] = len(entry["choices"])
            if entry.get("next"):
                summary["next"] = str(entry["next"])

        if not node_id:
            return None
        if node_type:
            node_type = node_type.strip()
        return _ScenarioNode(
            node_id=node_id.strip(),
            label=(label.strip() if isinstance(label, str) else None),
            node_type=node_type,
            summary=summary,
        )

    nodes_iterable: Iterable[Any]
    if hasattr(scenario, "nodes"):
        nodes_iterable = getattr(scenario, "nodes")
    elif isinstance(scenario, Mapping):
        raw_nodes = scenario.get("nodes")
        nodes_iterable = raw_nodes if isinstance(raw_nodes, Iterable) else ()
    else:
        nodes_iterable = ()

    lookup: Dict[str, _ScenarioNode] = {}
    for entry in nodes_iterable:
        normalised = _normalise_entry(entry)
        if normalised is None:
            continue
        lookup[normalised.node_id] = normalised
    return lookup


def _build_node_details(
    node_ids: Iterable[str],
    lookup: Mapping[str, _ScenarioNode],
) -> Dict[str, Dict[str, Any]]:
    details: Dict[str, Dict[str, Any]] = {}
    seen: set[str] = set()
    for node_id in node_ids:
        if node_id in seen:
            continue
        seen.add(node_id)
        payload: Dict[str, Any] = {"id": node_id}
        entry = lookup.get(node_id)
        if entry is not None:
            if entry.label:
                payload["label"] = entry.label
            if entry.node_type:
                payload["type"] = entry.node_type
            if entry.summary:
                payload["summary"] = entry.summary
        details[node_id] = payload
    return details


def _choice_delta(
    a: Mapping[str, Dict[str, Any]],
    b: Mapping[str, Dict[str, Any]],
) -> Dict[str, list[Dict[str, Any]]]:
    changes: list[Dict[str, Any]] = []
    added: list[Dict[str, Any]] = []
    removed: list[Dict[str, Any]] = []

    povs = set(a.keys()).union(b.keys())
    for pov in sorted(povs):
        entries_a = a.get(pov, {})
        entries_b = b.get(pov, {})
        nodes_a = set(entries_a.keys())
        nodes_b = set(entries_b.keys())

        for node_id in sorted(nodes_a & nodes_b):
            value_a = entries_a[node_id]
            value_b = entries_b[node_id]
            if value_a != value_b:
                changes.append(
                    {
                        "pov": pov,
                        "node": node_id,
                        "source": value_a,
                        "target": value_b,
                    }
                )

        for node_id in sorted(nodes_a - nodes_b):
            added.append({"pov": pov, "node": node_id, "value": entries_a[node_id]})

        for node_id in sorted(nodes_b - nodes_a):
            removed.append({"pov": pov, "node": node_id, "value": entries_b[node_id]})

    return {"changed": changes, "added": added, "removed": removed}


def _asset_delta(
    world_a: Worldline,
    world_b: Worldline,
) -> Dict[str, Sequence[str]]:
    assets_a = world_a.metadata.get("assets")
    assets_b = world_b.metadata.get("assets")

    set_a = {str(entry) for entry in assets_a or [] if entry is not None}
    set_b = {str(entry) for entry in assets_b or [] if entry is not None}
    return {
        "only_in_source": sorted(set_a - set_b),
        "only_in_target": sorted(set_b - set_a),
        "shared": sorted(set_a & set_b),
    }


def diff_worldline_scenes(
    source: str | Worldline,
    target: str | Worldline,
    *,
    registry: Optional[WorldlineRegistry] = None,
    mask_by_pov: bool = True,
    scenario: Any = None,
) -> Dict[str, Any]:
    """
    Produce a detailed diff between two worldlines with optional scene metadata.
    """

    registry = registry or WORLDLINES
    world_a = _resolve_worldline(source, registry)
    world_b = _resolve_worldline(target, registry)

    base_diff = diff_worlds(
        world_a,
        world_b,
        registry=registry,
        mask_by_pov=mask_by_pov,
    )

    choice_map_a = _filter_choices(world_a, mask_by_pov)
    choice_map_b = _filter_choices(world_b, mask_by_pov)

    choice_changes = _choice_delta(choice_map_a, choice_map_b)
    asset_changes = _asset_delta(world_a, world_b)

    ordered_a = _order_nodes(world_a)
    ordered_b = _order_nodes(world_b)
    union_nodes = set(ordered_a) | set(ordered_b)

    scenario_lookup = _scenario_lookup(scenario)
    node_details = _build_node_details(union_nodes, scenario_lookup)

    node_changes = {
        "added": base_diff["nodes"]["only_in_a"],
        "removed": base_diff["nodes"]["only_in_b"],
        "shared": base_diff["nodes"]["shared"],
        "changed": [entry["node"] for entry in choice_changes["changed"]],
    }

    result: Dict[str, Any] = {
        "ok": True,
        "source": base_diff["world_a"],
        "target": base_diff["world_b"],
        "node_changes": node_changes,
        "choices": base_diff["choices"],
        "choice_changes": choice_changes,
        "assets": base_diff["assets"],
        "asset_changes": asset_changes,
        "timeline": {
            "source": ordered_a,
            "target": ordered_b,
            "overlap": sorted(union_nodes),
        },
        "node_details": node_details,
    }

    return result
