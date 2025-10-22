from __future__ import annotations

"""
Worldline registry for managing POV-aware timeline forks.

The registry keeps lightweight metadata for each worldline and provides helpers
for switching the active world so the global POV manager stays in sync.
"""

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    from comfyvn.core import modder_hooks
except Exception:  # pragma: no cover - optional import for headless tools
    modder_hooks = None  # type: ignore

try:
    from comfyvn import __version__ as COMFYVN_VERSION
except Exception:  # pragma: no cover - defensive import fallback
    COMFYVN_VERSION = "0.0.0"

from .manager import POV, POVManager

__all__ = [
    "Worldline",
    "WorldlineRegistry",
    "WORLDLINES",
    "LANE_COLORS",
    "LANE_LABELS",
    "DEFAULT_SNAPSHOT_TOOL",
    "create_world",
    "list_worlds",
    "get_world",
    "switch_world",
    "update_world",
    "active_world",
    "record_snapshot",
    "make_snapshot_cache_key",
]

LOGGER = logging.getLogger(__name__)

LANE_OFFICIAL = "official"
LANE_VN_BRANCH = "vn_branch"
LANE_SCRATCH = "scratch"

LANE_ALIASES = {
    "canon": LANE_OFFICIAL,
    "main": LANE_OFFICIAL,
    "vn": LANE_VN_BRANCH,
    "branch": LANE_VN_BRANCH,
    "side": LANE_VN_BRANCH,
    "scratch": LANE_SCRATCH,
    "sandbox": LANE_SCRATCH,
    "experimental": LANE_SCRATCH,
}

LANE_LABELS = {
    LANE_OFFICIAL: "Official",
    LANE_VN_BRANCH: "VN Branch",
    LANE_SCRATCH: "Scratch",
}

LANE_COLORS = {
    LANE_OFFICIAL: "#D4AF37",  # Gold
    LANE_VN_BRANCH: "#1E6FFF",  # Blue
    LANE_SCRATCH: "#7A7A7A",  # Gray
}

SNAPSHOT_KEY_FIELDS = (
    "scene",
    "node",
    "worldline",
    "pov",
    "vars",
    "seed",
    "theme",
    "weather",
)

DELTA_SCHEMA_VERSION = "v1"
META_DELTA_KEY = "_wl_delta"
META_DELTA_BASE = "_wl_delta_base"
META_DELTA_SCHEMA = "_wl_delta_schema"
DELTA_SKIP_KEYS = {"snapshots"}
DEFAULT_SNAPSHOT_TOOL = "comfyvn.snapshot"


def _register_modder_hooks() -> None:
    if modder_hooks is None:
        return
    spec_map = modder_hooks.HOOK_SPECS
    if "on_worldline_created" not in spec_map:
        spec_map["on_worldline_created"] = modder_hooks.HookSpec(
            name="on_worldline_created",
            description="Emitted when a new worldline lane is created or forked.",
            payload_fields={
                "id": "Identifier assigned to the worldline.",
                "label": "Human readable label for the lane.",
                "lane": "Lane bucket (official|vn_branch|scratch).",
                "parent_id": "Source worldline identifier if forked.",
                "pov": "Primary POV associated with the lane.",
                "root_node": "Root node identifier used for the lane.",
                "metadata": "Metadata payload stored alongside the worldline.",
                "created_at": "Creation timestamp (UTC ISO8601).",
                "delta": "Delta metadata relative to the parent lane (if any).",
            },
            ws_topic="modder.on_worldline_created",
            rest_event="on_worldline_created",
        )
    if "on_snapshot" not in spec_map:
        spec_map["on_snapshot"] = modder_hooks.HookSpec(
            name="on_snapshot",
            description="Published when a timeline snapshot thumbnail is captured.",
            payload_fields={
                "worldline": "Worldline identifier the snapshot belongs to.",
                "node": "Node identifier recorded for the snapshot.",
                "scene": "Scene identifier recorded for the snapshot.",
                "lane": "Lane bucket (official|vn_branch|scratch).",
                "lane_color": "Hex colour associated with the lane.",
                "thumbnail": "Relative path to the persisted thumbnail asset.",
                "cache_key": "Deterministic cache key derived from snapshot state.",
                "hash": "Content hash recorded for the thumbnail image.",
                "pov": "POV associated with the snapshot payload.",
                "metadata": "Additional metadata persisted with the snapshot.",
                "captured_at": "UTC ISO8601 timestamp when the snapshot was recorded.",
                "workflow_hash": "Deterministic workflow hash derived from snapshot inputs.",
                "sidecar": "Sidecar metadata including tool, version, workflow hash, and capture context.",
            },
            ws_topic="modder.on_snapshot",
            rest_event="on_snapshot",
        )


_register_modder_hooks()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_nodes(metadata: Mapping[str, Any]) -> List[str]:
    """
    Return a sorted list of branch node identifiers recorded in the metadata.

    Worldline metadata may expose any of the following keys:
    - ``nodes``: canonical list of node identifiers.
    - ``branch_nodes`` / ``touched_nodes``: alternate labels used by older chats.
    - ``timeline``: optional mapping with a ``nodes`` entry.
    """

    candidates: Iterable[Any] = ()
    if isinstance(metadata.get("nodes"), Iterable):
        candidates = metadata.get("nodes")  # type: ignore[assignment]
    elif isinstance(metadata.get("branch_nodes"), Iterable):
        candidates = metadata.get("branch_nodes")  # type: ignore[assignment]
    elif isinstance(metadata.get("touched_nodes"), Iterable):
        candidates = metadata.get("touched_nodes")  # type: ignore[assignment]
    elif isinstance(metadata.get("timeline"), Mapping):
        timeline = metadata.get("timeline")
        if isinstance(timeline, Mapping):
            entry = timeline.get("nodes")
            if isinstance(entry, Iterable):
                candidates = entry  # type: ignore[assignment]

    nodes: List[str] = []
    for value in candidates or []:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            nodes.append(text)
    return sorted(dict.fromkeys(nodes))


def _normalise_choices(metadata: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Return a stable mapping of POV → node_id → choice metadata.

    Expected metadata layouts:
    - ``choices``: {pov_id: {node_id: value}}
    - ``branch_states`` or ``decision_log`` share the same shape.
    """

    raw = metadata.get("choices")
    if not isinstance(raw, Mapping):
        if isinstance(metadata.get("branch_states"), Mapping):
            raw = metadata.get("branch_states")  # type: ignore[assignment]
        elif isinstance(metadata.get("decision_log"), Mapping):
            raw = metadata.get("decision_log")  # type: ignore[assignment]
        else:
            raw = {}

    choices: Dict[str, Dict[str, Any]] = {}
    for pov_key, pov_payload in raw.items():
        pov_id = str(pov_key).strip()
        if not pov_id:
            continue
        pov_choices: Dict[str, Any] = {}
        if isinstance(pov_payload, Mapping):
            for node_id, value in pov_payload.items():
                node_key = str(node_id).strip()
                if not node_key:
                    continue
                pov_choices[node_key] = value
        elif isinstance(pov_payload, Iterable):
            for entry in pov_payload:
                if not isinstance(entry, Mapping):
                    continue
                node_id = str(entry.get("node") or entry.get("id") or "").strip()
                if not node_id:
                    continue
                pov_choices[node_id] = entry.get("value")
        if pov_choices:
            choices[pov_id] = pov_choices
    return choices


def _normalise_lane(lane: Optional[str], *, world_id: Optional[str] = None) -> str:
    if isinstance(lane, str):
        key = lane.strip().lower().replace(" ", "_")
        if key in LANE_COLORS:
            return key
        if key in LANE_ALIASES:
            return LANE_ALIASES[key]
    if world_id:
        lowered = world_id.strip().lower()
        if lowered in {"official", "canon", "main"}:
            return LANE_OFFICIAL
        if lowered in {"vn", "branch"}:
            return LANE_VN_BRANCH
    return LANE_SCRATCH


def _lane_color(lane: str) -> str:
    return LANE_COLORS.get(lane, LANE_COLORS[LANE_SCRATCH])


def _lane_label(lane: str) -> str:
    return LANE_LABELS.get(lane, LANE_LABELS[LANE_SCRATCH])


def _ensure_lane_metadata(
    metadata: Dict[str, Any], lane: str, parent_id: Optional[str]
) -> None:
    metadata.setdefault("lane", lane)
    if parent_id:
        metadata.setdefault("parent_id", parent_id)


def _clean_metadata(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    if not isinstance(payload, Mapping):
        return cleaned
    for key, value in payload.items():
        if key in {META_DELTA_KEY, META_DELTA_BASE, META_DELTA_SCHEMA}:
            continue
        cleaned[key] = deepcopy(value)
    return cleaned


def _merge_metadata(
    parent: Optional["Worldline"],
    overlay: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    parent_meta = _clean_metadata(parent.metadata if parent else None)
    overlay_meta = _clean_metadata(overlay)
    resolved: Dict[str, Any] = deepcopy(parent_meta)
    delta: Dict[str, Any] = {}

    for key, value in overlay_meta.items():
        resolved[key] = deepcopy(value)
        if key in DELTA_SKIP_KEYS:
            continue
        base_value = parent_meta.get(key)
        if base_value != value:
            delta[key] = deepcopy(value)

    if parent:
        resolved[META_DELTA_BASE] = parent.id
        resolved[META_DELTA_SCHEMA] = DELTA_SCHEMA_VERSION
        resolved[META_DELTA_KEY] = delta
    elif overlay_meta:
        resolved[META_DELTA_SCHEMA] = DELTA_SCHEMA_VERSION
        resolved[META_DELTA_KEY] = delta
    else:
        resolved.pop(META_DELTA_KEY, None)
        resolved.pop(META_DELTA_SCHEMA, None)

    return resolved


def make_snapshot_cache_key(**kwargs: Any) -> str:
    """
    Build a deterministic cache key for timeline snapshots.

    Required keyword arguments: scene, node, worldline, pov, vars, seed, theme, weather.
    The ``vars`` payload is canonicalised to a stable hash to keep the key compact.
    """

    missing = [field for field in SNAPSHOT_KEY_FIELDS if field not in kwargs]
    if missing:
        raise ValueError(f"missing snapshot key fields: {', '.join(missing)}")
    serialisable = dict(kwargs)
    vars_payload = serialisable.pop("vars")
    try:
        vars_dump = json.dumps(vars_payload, sort_keys=True, separators=(",", ":"))
    except TypeError as exc:  # pragma: no cover - defensive
        raise ValueError("snapshot vars payload must be JSON serialisable") from exc
    digest = hashlib.sha256(vars_dump.encode("utf-8")).hexdigest()
    serialisable["vars_digest"] = digest
    key_parts = [
        str(serialisable["scene"]).strip(),
        str(serialisable["node"]).strip(),
        str(serialisable["worldline"]).strip(),
        str(serialisable["pov"]).strip(),
        str(serialisable["seed"]).strip(),
        str(serialisable["theme"]).strip(),
        str(serialisable["weather"]).strip(),
        digest,
    ]
    return ":".join(part or "_" for part in key_parts)


@dataclass(slots=True)
class Worldline:
    id: str
    label: str
    pov: str
    root_node: str
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    lane: str = LANE_SCRATCH
    parent_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def snapshot(self, *, include_metadata: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "pov": self.pov,
            "root_node": self.root_node,
            "notes": self.notes,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
            "lane": self.lane,
            "lane_color": _lane_color(self.lane),
            "lane_label": _lane_label(self.lane),
        }
        if self.parent_id:
            payload["parent_id"] = self.parent_id
        if include_metadata:
            payload["metadata"] = self.metadata.copy()
        delta = self.delta()
        if delta:
            payload["delta"] = delta
        return payload

    def update(
        self,
        *,
        label: Optional[str] = None,
        pov: Optional[str] = None,
        root_node: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        lane: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> None:
        if label is not None:
            self.label = label
        if pov is not None:
            self.pov = pov
        if root_node is not None:
            self.root_node = root_node
        if notes is not None:
            self.notes = notes
        if metadata is not None:
            self.metadata = dict(metadata)
        if lane is not None:
            self.lane = _normalise_lane(lane, world_id=self.id)
        if parent_id is not None:
            self.parent_id = parent_id
        _ensure_lane_metadata(self.metadata, self.lane, self.parent_id)
        self.updated_at = _utc_now()

    def branch_nodes(self) -> List[str]:
        return _normalise_nodes(self.metadata)

    def choice_map(self) -> Dict[str, Dict[str, Any]]:
        return _normalise_choices(self.metadata)

    @property
    def lane_color(self) -> str:
        return _lane_color(self.lane)

    @property
    def lane_label(self) -> str:
        return _lane_label(self.lane)

    def delta(self) -> Dict[str, Any]:
        delta_payload = self.metadata.get(META_DELTA_KEY)
        if isinstance(delta_payload, Mapping):
            return dict(delta_payload)
        return {}


class WorldlineRegistry:
    """
    Thread-safe worldline registry coordinating with the global POV manager.
    """

    def __init__(self, manager: Optional[POVManager] = None) -> None:
        self._lock = RLock()
        self._worlds: Dict[str, Worldline] = {}
        self._active: Optional[str] = None
        self._manager = manager or POV

    # ---------------------------------------------------------------- manager
    def attach_manager(self, manager: POVManager) -> None:
        if not isinstance(manager, POVManager):
            raise TypeError("manager must be a POVManager instance")
        with self._lock:
            self._manager = manager

    # ---------------------------------------------------------------- helpers
    def _ensure_world_id(self, world_id: str) -> str:
        key = str(world_id or "").strip()
        if not key:
            raise ValueError("world id must be a non-empty string")
        return key

    def _activate(self, world: Worldline) -> Dict[str, Any]:
        snapshot = self._manager.set(world.pov)
        self._active = world.id
        world.updated_at = _utc_now()
        return snapshot

    def ensure(self, world_id: str) -> Worldline:
        key = self._ensure_world_id(world_id)
        with self._lock:
            world = self._worlds.get(key)
            if world is None:
                raise KeyError(f"world '{key}' is not registered")
            return world

    # ---------------------------------------------------------------- actions
    def create_or_update(
        self,
        world_id: str,
        *,
        label: Optional[str] = None,
        pov: Optional[str] = None,
        root_node: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        lane: Optional[str] = None,
        parent_id: Optional[str] = None,
        set_active: bool = False,
    ) -> Tuple[Worldline, bool, Optional[Dict[str, Any]]]:
        """
        Add or update a worldline entry.

        Returns (world, created_flag, pov_snapshot_if_activated).
        """

        key = self._ensure_world_id(world_id)
        label_value = label if label is not None else key
        pov_value = pov if pov is not None else "narrator"
        root_value = root_node if root_node is not None else "start"
        lane_value = _normalise_lane(lane, world_id=key)
        parent_supplied = parent_id is not None

        hook_payload: Optional[Dict[str, Any]] = None
        with self._lock:
            existing = self._worlds.get(key)
            existing_parent = existing.parent_id if existing else None
            if parent_supplied:
                parent_lookup_id = str(parent_id or "").strip() or None
            else:
                parent_lookup_id = existing_parent
            parent_world: Optional[Worldline] = None
            if parent_lookup_id:
                parent_world = self._worlds.get(parent_lookup_id)
                if parent_world is None:
                    raise KeyError(
                        f"parent world '{parent_lookup_id}' is not registered"
                    )

            metadata_required = (
                existing is None
                or metadata is not None
                or (parent_supplied and parent_lookup_id != existing_parent)
            )
            meta_payload: Optional[Dict[str, Any]] = None
            if metadata_required:
                if metadata is not None:
                    overlay_source: Optional[Mapping[str, Any]] = metadata
                elif existing is not None:
                    overlay_source = existing.metadata
                else:
                    overlay_source = None
                meta_payload = _merge_metadata(parent_world, overlay_source)
                _ensure_lane_metadata(meta_payload, lane_value, parent_lookup_id)
            if existing is None:
                world = Worldline(
                    id=key,
                    label=label_value,
                    pov=pov_value,
                    root_node=root_value,
                    notes=notes or "",
                    metadata=meta_payload or {},
                    lane=lane_value,
                    parent_id=parent_lookup_id,
                )
                self._worlds[key] = world
                created = True
            else:
                existing.update(
                    label=label,
                    pov=pov,
                    root_node=root_node,
                    notes=notes,
                    metadata=meta_payload,
                    lane=lane,
                    parent_id=parent_id if parent_supplied else None,
                )
                world = existing
                created = False
            pov_snapshot: Optional[Dict[str, Any]] = None
            if set_active:
                pov_snapshot = self._activate(world)
            if created:
                hook_payload = world.snapshot()
        if created and hook_payload and modder_hooks is not None:
            try:
                modder_hooks.emit("on_worldline_created", hook_payload)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "Failed to emit on_worldline_created for %s", key, exc_info=True
                )
        if created:
            LOGGER.info(
                "Worldline created: id=%s lane=%s pov=%s root=%s",
                world.id,
                world.lane,
                world.pov,
                world.root_node,
            )
        return world, created, pov_snapshot

    def update(
        self,
        world_id: str,
        *,
        label: Optional[str] = None,
        pov: Optional[str] = None,
        root_node: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        lane: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Worldline:
        self.ensure(world_id)
        world, _created, _snapshot = self.create_or_update(
            world_id,
            label=label,
            pov=pov,
            root_node=root_node,
            notes=notes,
            metadata=metadata,
            lane=lane,
            parent_id=parent_id,
            set_active=False,
        )
        return world

    def switch(self, world_id: str) -> Tuple[Worldline, Dict[str, Any]]:
        world = self.ensure(world_id)
        with self._lock:
            snapshot = self._activate(world)
            return world, snapshot

    def reset(self) -> None:
        with self._lock:
            self._worlds.clear()
            self._active = None

    def fork(
        self,
        source_id: str,
        new_world_id: str,
        *,
        label: Optional[str] = None,
        lane: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        set_active: bool = False,
    ) -> Tuple[Worldline, bool, Optional[Dict[str, Any]]]:
        source = self.ensure(source_id)
        label_value = label or f"{source.label} Fork"
        lane_value = _normalise_lane(lane, world_id=new_world_id)
        world, created, snapshot = self.create_or_update(
            new_world_id,
            label=label_value,
            pov=source.pov,
            root_node=source.root_node,
            notes=notes if notes is not None else source.notes,
            metadata=metadata,
            lane=lane_value,
            parent_id=source.id,
            set_active=set_active,
        )
        if created:
            LOGGER.info(
                "Forked worldline '%s' from '%s' (lane=%s)",
                world.id,
                source.id,
                world.lane,
            )
        return world, created, snapshot

    def record_snapshot(
        self,
        world_id: str,
        snapshot_entry: Mapping[str, Any],
        *,
        dedupe: bool = True,
        limit: Optional[int] = 250,
    ) -> Dict[str, Any]:
        world = self.ensure(world_id)
        entry = dict(snapshot_entry)
        cache_key = entry.get("cache_key")
        if not cache_key:
            raise ValueError("snapshot entry requires a cache_key field")
        entry.setdefault("captured_at", _utc_now().isoformat().replace("+00:00", "Z"))
        entry.setdefault("worldline", world.id)
        entry.setdefault("lane", world.lane)
        entry.setdefault("lane_color", world.lane_color)
        entry.setdefault("pov", world.pov)
        entry.setdefault("lane_label", world.lane_label)

        raw_metadata = entry.get("metadata")
        if isinstance(raw_metadata, Mapping):
            metadata_ref = dict(raw_metadata)
        else:
            metadata_ref = {}
        entry["metadata"] = metadata_ref

        workflow_hash_value = entry.get("workflow_hash")
        if not isinstance(workflow_hash_value, str) or not workflow_hash_value.strip():
            candidate = metadata_ref.get("workflow_hash")
            if isinstance(candidate, str) and candidate.strip():
                workflow_hash_value = candidate.strip()
            else:
                workflow_hash_value = hashlib.sha256(
                    cache_key.encode("utf-8")
                ).hexdigest()
        else:
            workflow_hash_value = workflow_hash_value.strip()
        entry["workflow_hash"] = workflow_hash_value

        metadata_ref.setdefault("workflow_hash", workflow_hash_value)
        metadata_ref.setdefault(
            "tool", metadata_ref.get("tool") or DEFAULT_SNAPSHOT_TOOL
        )
        metadata_ref.setdefault(
            "version", metadata_ref.get("version") or COMFYVN_VERSION
        )
        metadata_ref.setdefault("worldline", world.id)
        metadata_ref.setdefault("pov", entry.get("pov", world.pov))
        metadata_ref.setdefault("theme", entry.get("theme", ""))
        metadata_ref.setdefault("weather", entry.get("weather", ""))
        metadata_ref.setdefault("seed", entry.get("seed", 0))
        metadata_ref.setdefault("vars_digest", entry.get("vars_digest"))
        metadata_ref.setdefault("lane", world.lane)
        metadata_ref.setdefault("lane_color", world.lane_color)

        sidecar_existing = entry.get("sidecar")
        if isinstance(sidecar_existing, Mapping):
            sidecar_payload = dict(sidecar_existing)
        else:
            sidecar_payload = {}
        sidecar_payload.setdefault(
            "tool", metadata_ref.get("tool", DEFAULT_SNAPSHOT_TOOL)
        )
        sidecar_payload.setdefault(
            "version", metadata_ref.get("version", COMFYVN_VERSION)
        )
        sidecar_payload.setdefault("workflow_hash", workflow_hash_value)
        sidecar_payload.setdefault("seed", entry.get("seed", 0))
        sidecar_payload.setdefault("worldline", world.id)
        sidecar_payload.setdefault("pov", entry.get("pov", world.pov))
        sidecar_payload.setdefault("theme", entry.get("theme", ""))
        sidecar_payload.setdefault("weather", entry.get("weather", ""))
        sidecar_payload.setdefault("vars_digest", entry.get("vars_digest"))
        sidecar_payload.setdefault("cache_key", cache_key)
        sidecar_payload.setdefault("lane", world.lane)
        sidecar_payload.setdefault("lane_color", world.lane_color)
        sidecar_payload.setdefault("lane_label", world.lane_label)
        sidecar_payload.setdefault("captured_at", entry.get("captured_at"))
        sidecar_payload.setdefault("thumbnail", entry.get("thumbnail"))
        sidecar_payload.setdefault("thumbnail_hash", entry.get("hash"))
        entry["sidecar"] = sidecar_payload
        with self._lock:
            snapshots = list(world.metadata.get("snapshots") or [])
            if dedupe:
                snapshots = [
                    item for item in snapshots if item.get("cache_key") != cache_key
                ]
            snapshots.append(entry)
            if limit and limit > 0:
                snapshots = snapshots[-limit:]
            world.metadata["snapshots"] = snapshots
            world.updated_at = _utc_now()
        if modder_hooks is not None:
            try:
                modder_hooks.emit("on_snapshot", dict(entry))
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "Failed to emit on_snapshot for worldline %s",
                    world.id,
                    exc_info=True,
                )
        LOGGER.debug(
            "Recorded snapshot for worldline %s node=%s cache_key=%s",
            world.id,
            entry.get("node"),
            cache_key,
        )
        return entry

    # ---------------------------------------------------------------- queries
    def list(self) -> List[Worldline]:
        with self._lock:
            return list(self._worlds.values())

    def list_payloads(self) -> List[Dict[str, Any]]:
        with self._lock:
            active_id = self._active
            payloads: List[Dict[str, Any]] = []
            for world in self._worlds.values():
                snapshot = world.snapshot()
                snapshot["active"] = world.id == active_id
                payloads.append(snapshot)
            return payloads

    def active_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._active:
                return None
            world = self._worlds.get(self._active)
            if world is None:
                return None
            snapshot = world.snapshot()
            snapshot["active"] = True
            return snapshot


WORLDLINES = WorldlineRegistry(POV)


def create_world(
    world_id: str,
    label: Optional[str] = None,
    pov: Optional[str] = None,
    root_node: Optional[str] = None,
    *,
    notes: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    activate: bool = False,
) -> Dict[str, Any]:
    world, _created, _snapshot = WORLDLINES.create_or_update(
        world_id,
        label=label,
        pov=pov,
        root_node=root_node,
        notes=notes,
        metadata=metadata,
        set_active=activate,
    )
    return world.snapshot()


def list_worlds() -> List[Dict[str, Any]]:
    return WORLDLINES.list_payloads()


def get_world(world_id: str) -> Dict[str, Any]:
    world = WORLDLINES.ensure(world_id)
    return world.snapshot()


def switch_world(world_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    world, snapshot = WORLDLINES.switch(world_id)
    return world.snapshot(), snapshot


def update_world(
    world_id: str,
    *,
    label: Optional[str] = None,
    pov: Optional[str] = None,
    root_node: Optional[str] = None,
    notes: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    world = WORLDLINES.update(
        world_id,
        label=label,
        pov=pov,
        root_node=root_node,
        notes=notes,
        metadata=metadata,
    )
    return world.snapshot()


def record_snapshot(
    world_id: str,
    snapshot_entry: Mapping[str, Any],
    *,
    dedupe: bool = True,
    limit: Optional[int] = 250,
) -> Dict[str, Any]:
    return WORLDLINES.record_snapshot(
        world_id, snapshot_entry, dedupe=dedupe, limit=limit
    )


def active_world() -> Optional[Dict[str, Any]]:
    return WORLDLINES.active_snapshot()
