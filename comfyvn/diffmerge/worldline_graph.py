from __future__ import annotations

"""
Graph helpers for worldline timelines and merge previews.
"""

from typing import Any, Dict, List, Optional, Sequence

from comfyvn.pov.timeline_worlds import merge_worlds
from comfyvn.pov.worldlines import WORLDLINES, Worldline, WorldlineRegistry

from .scene_diff import _order_nodes, _resolve_worldline

__all__ = ["build_worldline_graph", "preview_worldline_merge"]


def _filter_worlds(
    registry: WorldlineRegistry,
    world_ids: Optional[Sequence[str]],
) -> list[Worldline]:
    if not world_ids:
        return registry.list()
    worlds: list[Worldline] = []
    for candidate in world_ids:
        try:
            worlds.append(_resolve_worldline(candidate, registry))
        except KeyError:
            continue
    return worlds


def _world_summary(
    world: Worldline, nodes: Sequence[str], *, active_id: Optional[str]
) -> Dict[str, Any]:
    return {
        "id": world.id,
        "label": world.label,
        "pov": world.pov,
        "root_node": world.root_node,
        "notes": world.notes,
        "node_count": len(nodes),
        "active": world.id == active_id,
        "metadata": {
            "assets": list(world.metadata.get("assets") or []),
            "hash": world.metadata.get("hash"),
        },
    }


def preview_worldline_merge(
    source: str | Worldline,
    target: str | Worldline,
    *,
    registry: Optional[WorldlineRegistry] = None,
) -> Dict[str, Any]:
    """
    Run a dry-run merge between two worldlines without mutating the registry.
    """

    registry = registry or WORLDLINES
    return merge_worlds(
        source,
        target,
        registry=registry,
        apply=False,
    )


def build_worldline_graph(
    *,
    target: str | None = None,
    world_ids: Optional[Sequence[str]] = None,
    registry: Optional[WorldlineRegistry] = None,
    include_fast_forward: bool = True,
) -> Dict[str, Any]:
    """
    Compile a lightweight graph representation of worldline timelines.
    """

    registry = registry or WORLDLINES
    worlds = _filter_worlds(registry, world_ids)
    active_snapshot = registry.active_snapshot()
    active_id = active_snapshot["id"] if active_snapshot else None

    if not worlds:
        return {
            "ok": True,
            "worlds": [],
            "graph": {"nodes": [], "edges": []},
            "timeline": {},
        }

    target_world: Optional[Worldline] = None
    if target:
        try:
            target_world = _resolve_worldline(target, registry)
        except KeyError:
            target_world = None
    if target_world is None:
        # Prefer the active world; fallback to the first in the list.
        if active_id:
            try:
                target_world = _resolve_worldline(active_id, registry)
            except KeyError:
                target_world = None
        if target_world is None:
            target_world = worlds[0]

    timeline_map: Dict[str, List[str]] = {}
    node_map: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    world_summaries: List[Dict[str, Any]] = []

    target_nodes: set[str] = set()
    if target_world is not None:
        target_nodes = set(_order_nodes(target_world))

    for world in worlds:
        ordered_nodes = _order_nodes(world)
        timeline_map[world.id] = ordered_nodes
        world_summaries.append(
            _world_summary(world, ordered_nodes, active_id=active_id)
        )
        previous_id: Optional[str] = None
        for index, node_id in enumerate(ordered_nodes):
            entry = node_map.setdefault(
                node_id,
                {
                    "id": node_id,
                    "worlds": [],
                },
            )
            attached_worlds: list[str] = entry["worlds"]
            if world.id not in attached_worlds:
                attached_worlds.append(world.id)
            if previous_id is not None:
                edges.append(
                    {
                        "world": world.id,
                        "source": previous_id,
                        "target": node_id,
                        "index": index - 1,
                    }
                )
            previous_id = node_id

    for world_entry in world_summaries:
        nodes = timeline_map.get(world_entry["id"], [])
        overlap = set(nodes) & target_nodes if target_nodes else set()
        world_entry["overlap"] = len(overlap)
        world_entry["divergence"] = (
            len(set(nodes) - target_nodes) if target_nodes else len(nodes)
        )

    fast_forward_map: Dict[str, Any] = {}
    if include_fast_forward and target_world is not None:
        for world in worlds:
            if world.id == target_world.id:
                continue
            preview = preview_worldline_merge(
                world,
                target_world,
                registry=registry,
            )
            if preview.get("ok"):
                fast_forward_map[world.id] = {
                    "ok": True,
                    "fast_forward": preview.get("fast_forward", False),
                    "added_nodes": preview.get("added_nodes", []),
                }
            else:
                fast_forward_map[world.id] = {
                    "ok": False,
                    "conflicts": preview.get("conflicts", []),
                }

    response: Dict[str, Any] = {
        "ok": True,
        "target": target_world.snapshot() if target_world else None,
        "worlds": world_summaries,
        "graph": {
            "nodes": list(node_map.values()),
            "edges": edges,
        },
        "timeline": timeline_map,
    }
    if fast_forward_map:
        response["fast_forward"] = fast_forward_map
    return response
