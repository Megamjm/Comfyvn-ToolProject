from __future__ import annotations

"""
Helpers for diffing and merging timeline-aware worldlines.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional, Tuple

from .worldlines import WORLDLINES, Worldline, WorldlineRegistry

__all__ = ["diff_worlds", "merge_worlds"]


def _resolve(
    candidate: str | Worldline,
    registry: WorldlineRegistry,
) -> Worldline:
    if isinstance(candidate, Worldline):
        return candidate
    return registry.ensure(candidate)


def _nodes(world: Worldline) -> set[str]:
    return set(world.branch_nodes())


def _choice_map(world: Worldline) -> Dict[str, Dict[str, Any]]:
    return world.choice_map()


def diff_worlds(
    source: str | Worldline,
    target: str | Worldline,
    *,
    registry: Optional[WorldlineRegistry] = None,
    mask_by_pov: bool = True,
) -> Dict[str, Any]:
    registry = registry or WORLDLINES
    world_a = _resolve(source, registry)
    world_b = _resolve(target, registry)

    nodes_a = _nodes(world_a)
    nodes_b = _nodes(world_b)

    choices_a = _choice_map(world_a)
    choices_b = _choice_map(world_b)

    def _filter_choices(
        world: Worldline, choices: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        if not mask_by_pov:
            return {pov: dict(entries) for pov, entries in choices.items()}
        pov_key = world.pov
        payload = choices.get(pov_key, {})
        return {pov_key: dict(payload)} if payload else {}

    return {
        "ok": True,
        "world_a": world_a.snapshot(),
        "world_b": world_b.snapshot(),
        "nodes": {
            "only_in_a": sorted(nodes_a - nodes_b),
            "only_in_b": sorted(nodes_b - nodes_a),
            "shared": sorted(nodes_a & nodes_b),
        },
        "choices": {
            "a": _filter_choices(world_a, choices_a),
            "b": _filter_choices(world_b, choices_b),
        },
        "assets": {
            "a": list(world_a.metadata.get("assets") or []),
            "b": list(world_b.metadata.get("assets") or []),
        },
    }


def merge_worlds(
    source: str | Worldline,
    target: str | Worldline,
    *,
    registry: Optional[WorldlineRegistry] = None,
    apply: bool = True,
) -> Dict[str, Any]:
    registry = registry or WORLDLINES
    world_source = _resolve(source, registry)
    world_target = _resolve(target, registry)

    nodes_source = _nodes(world_source)
    nodes_target = _nodes(world_target)

    choices_source = _choice_map(world_source)
    choices_target = _choice_map(world_target)

    conflicts = []
    for pov, entries in choices_target.items():
        source_entries = choices_source.get(pov, {})
        for node_id, target_value in entries.items():
            if node_id not in source_entries:
                continue
            source_value = source_entries[node_id]
            if source_value != target_value:
                conflicts.append(
                    {
                        "pov": pov,
                        "node": node_id,
                        "source": source_value,
                        "target": target_value,
                    }
                )

    if conflicts:
        return {
            "ok": False,
            "conflicts": conflicts,
            "world_a": world_source.snapshot(),
            "target": world_target.snapshot(),
        }

    merged_nodes = sorted(nodes_target.union(nodes_source))
    merged_choices = deepcopy(choices_source)
    for pov, entries in choices_target.items():
        merged_choices.setdefault(pov, {})
        merged_choices[pov].update(entries)

    fast_forward = nodes_target.issubset(nodes_source)
    if fast_forward:
        for pov, entries in choices_target.items():
            source_entries = choices_source.get(pov, {})
            for node_id, value in entries.items():
                if source_entries.get(node_id) != value:
                    fast_forward = False
                    break
            if not fast_forward:
                break

    new_metadata = deepcopy(world_target.metadata)
    new_metadata["nodes"] = merged_nodes
    if merged_choices:
        new_metadata["choices"] = merged_choices

    preview_snapshot = world_target.snapshot()
    preview_snapshot["metadata"] = dict(new_metadata)

    result: Dict[str, Any] = {
        "ok": True,
        "fast_forward": fast_forward,
        "source": world_source.snapshot(),
        "target": world_target.snapshot(),
        "target_preview": preview_snapshot,
        "added_nodes": sorted(nodes_source - nodes_target),
    }

    if apply:
        registry.update(
            world_target.id,
            metadata=new_metadata,
        )
        updated = registry.ensure(world_target.id)
        result["target"] = updated.snapshot()
        result["target_preview"] = result["target"]

    return result
