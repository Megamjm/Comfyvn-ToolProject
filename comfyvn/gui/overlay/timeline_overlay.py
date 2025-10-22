from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from comfyvn.config import feature_flags
from comfyvn.pov import WORLDLINES
from comfyvn.pov.timeline_worlds import diff_worlds
from comfyvn.pov.worldlines import LANE_COLORS, LANE_LABELS, Worldline

try:  # Optional integration; overlay still works without modder hooks.
    from comfyvn.core import modder_hooks
except Exception:  # pragma: no cover - optional dependency
    modder_hooks = None  # type: ignore

LOGGER = logging.getLogger(__name__)

LANE_PRIORITY = {
    "official": -1,
    "vn_branch": 0,
    "scratch": 1,
}


@dataclass
class TimelineOverlayNode:
    node: str
    scene: str
    cache_key: str
    hash: str
    thumbnail: Optional[str]
    badges: Dict[str, Any] = field(default_factory=dict)
    captured_at: Optional[str] = None
    vars_digest: Optional[str] = None
    seed: Any = None
    theme: Any = None
    weather: Any = None
    index: int = 0
    diff_badge: str = "shared"
    worldline: Optional[str] = None
    workflow_hash: Optional[str] = None
    sidecar: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "node": self.node,
            "scene": self.scene,
            "cache_key": self.cache_key,
            "hash": self.hash,
            "thumbnail": self.thumbnail,
            "badges": dict(self.badges),
            "captured_at": self.captured_at,
            "vars_digest": self.vars_digest,
            "seed": self.seed,
            "theme": self.theme,
            "weather": self.weather,
            "index": self.index,
            "diff_badge": self.diff_badge,
        }
        payload["pov_badge"] = self.badges.get("pov")
        payload["worldline"] = self.worldline
        payload["workflow_hash"] = self.workflow_hash
        if isinstance(self.sidecar, Mapping):
            payload["sidecar"] = dict(self.sidecar)
        else:
            payload["sidecar"] = self.sidecar
        return payload


@dataclass
class TimelineOverlayLane:
    id: str
    label: str
    lane: str
    lane_color: str
    lane_label: str
    parent_id: Optional[str]
    diff_base: Optional[str]
    diff_summary: Dict[str, int]
    delta: Dict[str, Any]
    snapshots: List[TimelineOverlayNode] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "lane": self.lane,
            "lane_color": self.lane_color,
            "lane_label": self.lane_label,
            "parent_id": self.parent_id,
            "diff": {
                "base": self.diff_base,
                "summary": dict(self.diff_summary),
            },
            "delta": dict(self.delta),
            "snapshots": [node.as_dict() for node in self.snapshots],
        }


class TimelineOverlayController:
    """
    Build a lane-aware overlay payload for the POV timeline view.

    The controller reads `WorldlineRegistry` metadata, decorates snapshots with diff
    badges, and exposes scrub helpers for quick navigation. Results are cached until
    invalidated by new modder hook events (`on_snapshot`, `on_worldline_created`).
    """

    def __init__(self, *, registry: Any = WORLDLINES, mask_by_pov: bool = True) -> None:
        self._registry = registry
        self._mask_by_pov = mask_by_pov
        self._lock = RLock()
        self._lanes_cache: Dict[str, TimelineOverlayLane] = {}
        self._diff_cache: Dict[Tuple[str, str, bool], Optional[Dict[str, Any]]] = {}
        self._hook_registered = False
        self.attach_hooks()

    # ---------------------------------------------------------------- utilities
    @property
    def enabled(self) -> bool:
        return feature_flags.is_enabled("enable_timeline_overlay", default=False)

    def attach_hooks(self) -> None:
        if self._hook_registered or modder_hooks is None:
            return

        def _listener(event: str, payload: Dict[str, Any]) -> None:
            if event == "on_snapshot":
                worldline = payload.get("worldline")
                self.invalidate(worldline if isinstance(worldline, str) else None)
            elif event == "on_worldline_created":
                self.invalidate(
                    payload.get("id") if isinstance(payload.get("id"), str) else None
                )

        try:
            modder_hooks.register_listener(
                _listener,
                events=("on_snapshot", "on_worldline_created"),
            )
            self._hook_registered = True
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug(
                "Timeline overlay modder hook registration failed", exc_info=True
            )

    def invalidate(self, worldline_id: Optional[str] = None) -> None:
        with self._lock:
            if worldline_id:
                self._lanes_cache.pop(worldline_id, None)
                self._diff_cache = {
                    key: value
                    for key, value in self._diff_cache.items()
                    if worldline_id not in key[:2]
                }
            else:
                self._lanes_cache.clear()
                self._diff_cache.clear()

    # ---------------------------------------------------------------- builders
    def state(self, *, refresh: bool = False) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "lanes": []}
        with self._lock:
            if refresh or not self._lanes_cache:
                self._lanes_cache = self._rebuild()
        lanes = sorted(
            (lane.as_dict() for lane in self._lanes_cache.values()),
            key=lambda payload: (
                LANE_PRIORITY.get(payload["lane"], 99),
                payload["label"].lower(),
            ),
        )
        return {"enabled": True, "lanes": lanes}

    def scrub(
        self,
        lane_id: str,
        *,
        cache_key: Optional[str] = None,
        step: int = 1,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        state = self.state()
        lane = next((lane for lane in state["lanes"] if lane["id"] == lane_id), None)
        if not lane:
            return None
        snapshots: List[Dict[str, Any]] = list(lane.get("snapshots") or [])
        if not snapshots:
            return None
        if cache_key:
            anchor = next(
                (
                    idx
                    for idx, snap in enumerate(snapshots)
                    if snap.get("cache_key") == cache_key
                ),
                0,
            )
        else:
            anchor = 0 if step >= 0 else len(snapshots) - 1
        index = max(0, min(len(snapshots) - 1, anchor + step))
        result = dict(snapshots[index])
        result["lane_id"] = lane_id
        result["lane_color"] = lane.get("lane_color")
        result["lane_label"] = lane.get("lane_label")
        return result

    # ---------------------------------------------------------------- internals
    def _rebuild(self) -> Dict[str, TimelineOverlayLane]:
        worlds: List[Worldline] = self._registry.list()
        official_id = next(
            (world.id for world in worlds if world.lane == "official"),
            None,
        )
        lanes: Dict[str, TimelineOverlayLane] = {}
        for world in worlds:
            base_id = world.parent_id or (
                official_id if world.lane != "official" else None
            )
            lane_payload = self._lane_payload(world, base_id)
            lanes[lane_payload.id] = lane_payload
        return lanes

    def _lane_payload(
        self, world: Worldline, base_id: Optional[str]
    ) -> TimelineOverlayLane:
        diff_payload = self._diff_payload(base_id, world.id) if base_id else None
        diff_summary, diff_badges = self._diff_summary(world, diff_payload)
        snapshots = [
            self._snapshot_payload(world, entry, index, diff_badges)
            for index, entry in enumerate(self._iter_snapshots(world))
        ]
        lane = TimelineOverlayLane(
            id=world.id,
            label=world.label,
            lane=world.lane,
            lane_color=LANE_COLORS.get(world.lane, "#7A7A7A"),
            lane_label=LANE_LABELS.get(world.lane, world.lane.title()),
            parent_id=world.parent_id,
            diff_base=base_id,
            diff_summary=diff_summary,
            delta=world.delta(),
            snapshots=[snapshot for snapshot in snapshots if snapshot is not None],
        )
        return lane

    def _iter_snapshots(self, world: Worldline) -> Iterable[Mapping[str, Any]]:
        raw = world.metadata.get("snapshots")
        if not isinstance(raw, list):
            return []
        cleaned: List[Mapping[str, Any]] = []
        for entry in raw:
            if isinstance(entry, Mapping):
                cleaned.append(entry)
        cleaned.sort(
            key=lambda entry: (
                str(entry.get("captured_at") or ""),
                str(entry.get("cache_key") or ""),
            )
        )
        return cleaned

    def _snapshot_payload(
        self,
        world: Worldline,
        entry: Mapping[str, Any],
        index: int,
        diff_badges: Mapping[str, str],
    ) -> Optional[TimelineOverlayNode]:
        node = str(entry.get("node") or "").strip()
        scene = str(entry.get("scene") or "").strip()
        cache_key = str(entry.get("cache_key") or "").strip()
        if not node or not scene or not cache_key:
            return None
        hash_value = str(entry.get("hash") or "").strip()
        badges_payload = entry.get("badges") or {}
        if isinstance(badges_payload, Mapping):
            badges = dict(badges_payload)
        else:
            badges = {}
        badges.setdefault("pov", entry.get("pov", world.pov))
        workflow_hash = entry.get("workflow_hash")
        if isinstance(workflow_hash, str):
            workflow_hash = workflow_hash.strip() or None
        else:
            workflow_hash = None
        sidecar_payload = entry.get("sidecar")
        sidecar: Optional[Dict[str, Any]]
        if isinstance(sidecar_payload, Mapping):
            sidecar = dict(sidecar_payload)
        else:
            sidecar = None
        worldline_id = str(entry.get("worldline") or world.id or "").strip() or world.id
        snapshot = TimelineOverlayNode(
            node=node,
            scene=scene,
            cache_key=cache_key,
            hash=hash_value,
            thumbnail=entry.get("thumbnail"),
            badges=badges,
            captured_at=entry.get("captured_at"),
            vars_digest=entry.get("vars_digest"),
            seed=entry.get("seed"),
            theme=entry.get("theme"),
            weather=entry.get("weather"),
            index=index,
            diff_badge=diff_badges.get(node, "shared"),
            worldline=worldline_id,
            workflow_hash=workflow_hash,
            sidecar=sidecar,
        )
        return snapshot

    def _diff_payload(
        self,
        base_id: str,
        target_id: str,
    ) -> Optional[Dict[str, Any]]:
        key = (base_id, target_id, self._mask_by_pov)
        cached = self._diff_cache.get(key)
        if cached is not None:
            return cached
        try:
            diff = diff_worlds(
                base_id,
                target_id,
                registry=self._registry,
                mask_by_pov=self._mask_by_pov,
            )
        except KeyError:
            diff = None
        self._diff_cache[key] = diff
        return diff

    def _diff_summary(
        self,
        world: Worldline,
        diff_payload: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, int], Dict[str, str]]:
        if not diff_payload:
            branches = world.branch_nodes()
            return (
                {
                    "added": 0,
                    "removed": 0,
                    "changed": 0,
                    "shared": len(branches),
                },
                {},
            )
        nodes_section = diff_payload.get("nodes") or {}
        added = set(nodes_section.get("only_in_b") or [])
        removed = set(nodes_section.get("only_in_a") or [])
        shared = set(nodes_section.get("shared") or [])
        choices = diff_payload.get("choices") or {}
        choices_a = choices.get("a") or {}
        choices_b = choices.get("b") or {}
        changed: set[str] = set()
        for pov_key, entries in choices_b.items():
            entries_a = choices_a.get(pov_key, {})
            for node_id, value in entries.items():
                if entries_a.get(node_id) != value:
                    changed.add(node_id)
        badge_map: Dict[str, str] = {}
        badge_map.update({node_id: "added" for node_id in added})
        badge_map.update({node_id: "removed" for node_id in removed})
        badge_map.update({node_id: "changed" for node_id in changed})
        summary = {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "shared": len(shared),
        }
        return summary, badge_map


OVERLAY = TimelineOverlayController()


def overlay_state(*, refresh: bool = False) -> Dict[str, Any]:
    return OVERLAY.state(refresh=refresh)


def scrub_lane(
    lane_id: str,
    *,
    cache_key: Optional[str] = None,
    step: int = 1,
) -> Optional[Dict[str, Any]]:
    return OVERLAY.scrub(lane_id, cache_key=cache_key, step=step)


__all__ = ["TimelineOverlayController", "OVERLAY", "overlay_state", "scrub_lane"]
