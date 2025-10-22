from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from fastapi import APIRouter, Body, HTTPException

from comfyvn import __version__ as COMFYVN_VERSION
from comfyvn.config import feature_flags

from ...pov import (
    WORLDLINES,
    diff_worlds,
    list_worlds,
    merge_worlds,
)
from ...pov import (
    active_world as get_active_world,
)
from ...pov import (
    switch_world as switch_worldline,
)
from ...pov.worldlines import DEFAULT_SNAPSHOT_TOOL, make_snapshot_cache_key

router = APIRouter(prefix="/api/pov", tags=["POV Worlds"])

LOGGER = logging.getLogger(__name__)


def _ensure_mapping(payload: Any, *, detail: str) -> MutableMapping[str, Any]:
    if isinstance(payload, MutableMapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


def _ensure_optional_mapping(
    payload: Optional[Any], *, detail: str
) -> Optional[Mapping[str, Any]]:
    if payload is None:
        return None
    if isinstance(payload, Mapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


def _worldlines_enabled() -> bool:
    return feature_flags.is_enabled("enable_worldlines", default=False)


def _require_worldlines_enabled() -> None:
    if not _worldlines_enabled():
        raise HTTPException(status_code=404, detail="worldlines feature disabled")


def _build_snapshot_entry(
    world_id: str,
    payload: Mapping[str, Any],
    *,
    default_pov: str,
) -> Dict[str, Any]:
    scene = payload.get("scene")
    node = payload.get("node")
    if not isinstance(scene, str) or not scene.strip():
        raise HTTPException(status_code=400, detail="snapshot.scene must be a string")
    if not isinstance(node, str) or not node.strip():
        raise HTTPException(status_code=400, detail="snapshot.node must be a string")

    pov = payload.get("pov") or default_pov
    if not isinstance(pov, str) or not pov.strip():
        raise HTTPException(status_code=400, detail="snapshot.pov must be a string")

    vars_payload = payload.get("vars") or {}
    if not isinstance(vars_payload, Mapping):
        raise HTTPException(status_code=400, detail="snapshot.vars must be an object")

    metadata_payload = _ensure_optional_mapping(
        payload.get("metadata"), detail="snapshot.metadata must be an object"
    )
    badges_payload = _ensure_optional_mapping(
        payload.get("badges"), detail="snapshot.badges must be an object"
    )

    try:
        cache_key = make_snapshot_cache_key(
            scene=scene.strip(),
            node=node.strip(),
            worldline=world_id,
            pov=pov.strip(),
            vars=vars_payload,
            seed=payload.get("seed", 0),
            theme=payload.get("theme", ""),
            weather=payload.get("weather", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    digest = cache_key.rsplit(":", 1)[-1]
    thumbnail = payload.get("thumbnail")
    if thumbnail is not None and not isinstance(thumbnail, str):
        raise HTTPException(
            status_code=400, detail="snapshot.thumbnail must be a string"
        )
    thumbnail_hash = payload.get("hash") or payload.get("thumbnail_hash")
    if thumbnail_hash is not None and not isinstance(thumbnail_hash, str):
        raise HTTPException(
            status_code=400, detail="snapshot.thumbnail_hash must be a string"
        )
    computed_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    if thumbnail_hash is None:
        thumbnail_hash = computed_hash
    else:
        thumbnail_hash = thumbnail_hash.strip() or computed_hash

    tool_name = str(
        payload.get("tool")
        or (metadata_payload or {}).get("tool")
        or DEFAULT_SNAPSHOT_TOOL
    )
    tool_version = str(
        payload.get("tool_version")
        or payload.get("version")
        or (metadata_payload or {}).get("version")
        or COMFYVN_VERSION
    )
    workflow_hash = payload.get("workflow_hash") or (
        (metadata_payload or {}).get("workflow_hash")
    )
    if not isinstance(workflow_hash, str) or not workflow_hash.strip():
        workflow_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    else:
        workflow_hash = workflow_hash.strip()

    metadata_dict = dict(metadata_payload or {})
    metadata_dict.setdefault("tool", tool_name)
    metadata_dict.setdefault("version", tool_version)
    metadata_dict.setdefault("workflow_hash", workflow_hash)
    metadata_dict.setdefault("worldline", world_id)
    metadata_dict.setdefault("pov", pov.strip())
    metadata_dict.setdefault("theme", payload.get("theme", ""))
    metadata_dict.setdefault("weather", payload.get("weather", ""))
    metadata_dict.setdefault("seed", payload.get("seed", 0))
    metadata_dict.setdefault("vars_digest", digest)

    entry: Dict[str, Any] = {
        "node": node.strip(),
        "scene": scene.strip(),
        "pov": pov.strip(),
        "cache_key": cache_key,
        "hash": thumbnail_hash,
        "thumbnail": thumbnail,
        "metadata": metadata_dict,
        "vars_digest": digest,
        "seed": payload.get("seed", 0),
        "theme": payload.get("theme", ""),
        "weather": payload.get("weather", ""),
    }
    entry["workflow_hash"] = workflow_hash
    entry["sidecar"] = {
        "tool": tool_name,
        "version": tool_version,
        "workflow_hash": workflow_hash,
        "seed": entry["seed"],
        "worldline": world_id,
        "pov": entry["pov"],
        "theme": entry["theme"],
        "weather": entry["weather"],
        "vars_digest": digest,
        "cache_key": cache_key,
    }

    if badges_payload:
        badges = dict(badges_payload)
    else:
        badges = {}
    badges.setdefault("pov", pov.strip())
    entry["badges"] = badges

    return entry


@router.get("/worlds")
async def get_worlds() -> Dict[str, Any]:
    enabled = _worldlines_enabled()
    if not enabled:
        return {
            "enabled": False,
            "items": [],
            "active": None,
        }
    return {
        "enabled": True,
        "items": list_worlds(),
        "active": get_active_world(),
    }


@router.post("/worlds")
async def create_or_update_world(payload: Any = Body(...)) -> Dict[str, Any]:
    _require_worldlines_enabled()
    data = _ensure_mapping(payload, detail="payload must be an object")
    world_id = data.get("id")
    if not isinstance(world_id, str) or not world_id.strip():
        raise HTTPException(status_code=400, detail="id must be a non-empty string")

    metadata_payload = _ensure_optional_mapping(
        data.get("metadata"), detail="metadata must be an object"
    )

    activate = bool(data.get("activate") or data.get("switch"))
    label = data.get("label")
    pov = data.get("pov")
    root_node = data.get("root_node")
    notes = data.get("notes")
    lane = data.get("lane")
    parent_id = data.get("parent_id")
    fork_from = data.get("fork_from")
    snapshot_payload = _ensure_optional_mapping(
        data.get("snapshot"), detail="snapshot must be an object"
    )

    metadata = dict(metadata_payload or {})
    snapshot_before = get_active_world()
    forked = False
    pov_snapshot: Optional[Dict[str, Any]] = None
    if isinstance(fork_from, str) and fork_from.strip():
        world_obj, created, pov_snapshot = WORLDLINES.fork(
            fork_from.strip(),
            world_id.strip(),
            label=label,
            lane=lane,
            notes=notes,
            metadata=metadata,
            set_active=activate,
        )
        forked = created
    else:
        world_obj, created, pov_snapshot = WORLDLINES.create_or_update(
            world_id.strip(),
            label=label,
            pov=pov,
            root_node=root_node,
            notes=notes,
            metadata=metadata,
            lane=lane,
            parent_id=parent_id,
            set_active=activate,
        )
    response: Dict[str, Any] = {
        "world": world_obj.snapshot(),
        "active": get_active_world(),
        "created": created,
    }
    if activate:
        response["pov"] = pov_snapshot or {}
    else:
        response["previous_active"] = snapshot_before

    diff_payload: Optional[Dict[str, Any]] = None
    base_world = parent_id or fork_from or world_obj.parent_id
    if base_world:
        try:
            diff_payload = diff_worlds(
                base_world,
                world_obj.id,
                mask_by_pov=bool(data.get("mask_pov", True)),
            )
        except KeyError:
            diff_payload = None
    if diff_payload:
        response["diff"] = diff_payload

    recorded_snapshot: Optional[Dict[str, Any]] = None
    if snapshot_payload:
        entry = _build_snapshot_entry(
            world_obj.id,
            snapshot_payload,
            default_pov=world_obj.pov,
        )
        recorded_snapshot = WORLDLINES.record_snapshot(world_obj.id, entry)
        response["snapshot"] = recorded_snapshot

    LOGGER.info(
        "worldline.upsert id=%s lane=%s created=%s activated=%s pov=%s wl=%s theme=%s weather=%s",
        world_obj.id,
        world_obj.lane,
        created,
        activate,
        world_obj.pov,
        response["active"]["id"] if response.get("active") else None,
        (recorded_snapshot or {}).get("theme"),
        (recorded_snapshot or {}).get("weather"),
    )
    response["forked"] = forked
    return response


@router.post("/worlds/switch")
async def switch_world(payload: Any = Body(...)) -> Dict[str, Any]:
    _require_worldlines_enabled()
    data = _ensure_mapping(payload, detail="payload must be an object")
    world_id = data.get("id")
    if not isinstance(world_id, str) or not world_id.strip():
        raise HTTPException(status_code=400, detail="id must be a non-empty string")
    snapshot_payload = _ensure_optional_mapping(
        data.get("snapshot"), detail="snapshot must be an object"
    )
    try:
        world, pov_snapshot = switch_worldline(world_id.strip())
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    recorded_snapshot: Optional[Dict[str, Any]] = None
    if snapshot_payload:
        entry = _build_snapshot_entry(
            world["id"],
            snapshot_payload,
            default_pov=world.get("pov", ""),
        )
        recorded_snapshot = WORLDLINES.record_snapshot(world["id"], entry)
    active_snapshot = get_active_world()
    LOGGER.info(
        "worldline.switch id=%s pov=%s wl=%s theme=%s weather=%s",
        world["id"],
        world.get("pov"),
        active_snapshot["id"] if active_snapshot else None,
        (recorded_snapshot or {}).get("theme"),
        (recorded_snapshot or {}).get("weather"),
    )
    response = {
        "world": world,
        "pov": pov_snapshot,
        "active": active_snapshot,
    }
    if recorded_snapshot:
        response["snapshot"] = recorded_snapshot
    return response


@router.post("/confirm_switch")
async def confirm_world_switch(payload: Any = Body(...)) -> Dict[str, Any]:
    _require_worldlines_enabled()
    data = _ensure_mapping(payload, detail="payload must be an object")
    target_id = data.get("id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise HTTPException(status_code=400, detail="id must be a non-empty string")

    fork_payload = _ensure_optional_mapping(
        data.get("fork"), detail="fork must be an object"
    )
    snapshot_payload = _ensure_optional_mapping(
        data.get("snapshot"), detail="snapshot must be an object"
    )
    mask_by_pov = bool(data.get("mask_pov", True))
    apply_switch = bool(data.get("apply", False))
    active_before = get_active_world()

    world_snapshot: Dict[str, Any]
    pov_snapshot: Optional[Dict[str, Any]] = None
    forked = False
    recorded_snapshot: Optional[Dict[str, Any]] = None

    if fork_payload:
        source_id = fork_payload.get("source") or target_id
        if not isinstance(source_id, str) or not source_id.strip():
            raise HTTPException(
                status_code=400, detail="fork.source must be a non-empty string"
            )
        fork_id = fork_payload.get("id")
        if not isinstance(fork_id, str) or not fork_id.strip():
            raise HTTPException(
                status_code=400, detail="fork.id must be a non-empty string"
            )
        fork_metadata = _ensure_optional_mapping(
            fork_payload.get("metadata"), detail="fork.metadata must be an object"
        )
        fork_snapshot_payload = _ensure_optional_mapping(
            fork_payload.get("snapshot"), detail="fork.snapshot must be an object"
        )
        world_obj, created, pov_snapshot = WORLDLINES.fork(
            source_id.strip(),
            fork_id.strip(),
            label=fork_payload.get("label"),
            lane=fork_payload.get("lane"),
            notes=fork_payload.get("notes"),
            metadata=fork_metadata,
            set_active=bool(fork_payload.get("activate", True)),
        )
        forked = created
        world_snapshot = world_obj.snapshot()
        if not data.get("compare_to"):
            data["compare_to"] = source_id
        if fork_snapshot_payload:
            entry = _build_snapshot_entry(
                world_obj.id,
                fork_snapshot_payload,
                default_pov=world_obj.pov,
            )
            recorded_snapshot = WORLDLINES.record_snapshot(world_obj.id, entry)
    else:
        if apply_switch:
            try:
                world_snapshot, pov_snapshot = switch_worldline(target_id.strip())
            except KeyError as exc:  # pragma: no cover - defensive
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        else:
            try:
                world_obj = WORLDLINES.ensure(target_id.strip())
            except KeyError as exc:  # pragma: no cover - defensive
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            world_snapshot = world_obj.snapshot()

        if snapshot_payload and apply_switch:
            entry = _build_snapshot_entry(
                world_snapshot["id"],
                snapshot_payload,
                default_pov=world_snapshot.get("pov", ""),
            )
            recorded_snapshot = WORLDLINES.record_snapshot(world_snapshot["id"], entry)

    compare_to = data.get("compare_to")
    if not isinstance(compare_to, str) or not compare_to.strip():
        compare_to = None
    if not compare_to and active_before and active_before.get("id"):
        previous_id = active_before["id"]
        if previous_id != world_snapshot["id"]:
            compare_to = previous_id

    diff_payload: Optional[Dict[str, Any]] = None
    if compare_to and compare_to != world_snapshot["id"]:
        try:
            diff_payload = diff_worlds(
                compare_to.strip(), world_snapshot["id"], mask_by_pov=mask_by_pov
            )
        except KeyError:
            diff_payload = None

    active_after = get_active_world()
    response: Dict[str, Any] = {
        "world": world_snapshot,
        "active": active_after if apply_switch or fork_payload else active_before,
        "pov": pov_snapshot,
        "forked": forked,
        "applied": apply_switch,
        "compare_to": compare_to,
    }
    if diff_payload:
        response["diff"] = diff_payload
    if recorded_snapshot:
        response["snapshot"] = recorded_snapshot

    active_ref = response.get("active")
    active_id = active_ref.get("id") if isinstance(active_ref, Mapping) else None
    LOGGER.info(
        "worldline.confirm id=%s apply=%s forked=%s pov=%s wl=%s theme=%s weather=%s",
        world_snapshot["id"],
        apply_switch,
        forked,
        world_snapshot.get("pov"),
        active_id,
        (recorded_snapshot or {}).get("theme"),
        (recorded_snapshot or {}).get("weather"),
    )
    return response


@router.post("/auto_bio_suggest")
async def auto_bio_suggest(payload: Any = Body(...)) -> Dict[str, Any]:
    _require_worldlines_enabled()
    data = _ensure_mapping(payload, detail="payload must be an object")

    world_ref = data.get("world") or data.get("worldline") or data.get("id")
    if isinstance(world_ref, str) and world_ref.strip():
        target_id = world_ref.strip()
    else:
        active = get_active_world()
        target_id = (
            str(active.get("id")).strip()
            if isinstance(active, Mapping) and isinstance(active.get("id"), str)
            else None
        )
    if not target_id:
        raise HTTPException(status_code=404, detail="no worldline available")

    try:
        world_obj = WORLDLINES.ensure(target_id)
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pov_value = data.get("pov") or world_obj.pov
    pov_text = pov_value.strip() if isinstance(pov_value, str) else world_obj.pov
    if not pov_text:
        pov_text = world_obj.pov
    mask_by_pov = bool(data.get("mask_pov", True))

    nodes = world_obj.branch_nodes()
    choice_map = world_obj.choice_map()
    if mask_by_pov:
        pov_choices = choice_map.get(pov_text, {})
    else:
        pov_choices = {
            node_id: meta
            for entries in choice_map.values()
            for node_id, meta in entries.items()
        }

    delta_payload = world_obj.delta()
    delta_nodes = []
    if isinstance(delta_payload.get("nodes"), list):
        delta_nodes = [
            str(item).strip() for item in delta_payload["nodes"] if str(item).strip()
        ]

    compare_to = data.get("compare_to") or world_obj.parent_id
    diff_payload: Optional[Dict[str, Any]] = None
    if (
        isinstance(compare_to, str)
        and compare_to.strip()
        and compare_to.strip() != world_obj.id
    ):
        try:
            diff_payload = diff_worlds(
                compare_to.strip(),
                world_obj.id,
                mask_by_pov=mask_by_pov,
            )
        except KeyError:
            diff_payload = None

    suggestions: List[Dict[str, Any]] = []
    suggestions.append(
        {
            "title": f"{world_obj.label} — {pov_text} POV",
            "summary": (
                f"Lane '{world_obj.lane_label}' tracks {len(nodes)} nodes and "
                f"{len(pov_choices)} POV-scoped decisions for {pov_text}."
            ),
            "confidence": 0.7,
            "source": "worldline",
        }
    )

    if delta_nodes:
        preview_nodes = ", ".join(delta_nodes[:3])
        overflow = max(0, len(delta_nodes) - 3)
        summary = f"New nodes since parent: {preview_nodes}"
        if overflow:
            summary += f" (+{overflow} more)"
        suggestions.append(
            {
                "title": "Delta nodes",
                "summary": summary,
                "confidence": 0.55,
                "source": "delta",
            }
        )

    snapshots = (
        world_obj.metadata.get("snapshots")
        if isinstance(world_obj.metadata, Mapping)
        else []
    )
    if isinstance(snapshots, list) and snapshots:
        latest = snapshots[-1]
        if isinstance(latest, Mapping):
            summary = (
                f"Latest snapshot at {latest.get('captured_at')} • node "
                f"{latest.get('node')} ({latest.get('scene')})"
            )
            suggestions.append(
                {
                    "title": "Recent snapshot",
                    "summary": summary,
                    "confidence": 0.5,
                    "source": "snapshots",
                }
            )

    diff_summary: Optional[Dict[str, int]] = None
    if diff_payload:
        nodes_section = diff_payload.get("nodes") or {}
        added = list(nodes_section.get("only_in_b") or [])
        removed = list(nodes_section.get("only_in_a") or [])
        choices_section = diff_payload.get("choices") or {}
        pov_section = choices_section.get("b") or {}
        if mask_by_pov:
            selected_choices = pov_section.get(pov_text, {})
            changed_choices = (
                len(selected_choices) if isinstance(selected_choices, Mapping) else 0
            )
        else:
            changed_choices = sum(
                len(entries) if isinstance(entries, Mapping) else 0
                for entries in pov_section.values()
            )
        diff_summary = {
            "added": len(added),
            "removed": len(removed),
            "changed_choices": changed_choices,
            "shared": len(nodes_section.get("shared") or []),
        }
        highlight_parts = []
        if added:
            highlight_parts.append(f"+{len(added)} nodes")
        if removed:
            highlight_parts.append(f"-{len(removed)} nodes")
        if changed_choices:
            highlight_parts.append(f"{changed_choices} choice updates")
        if highlight_parts:
            suggestions.append(
                {
                    "title": "Diff against base",
                    "summary": ", ".join(highlight_parts),
                    "confidence": 0.6,
                    "source": "diff",
                }
            )

    context: Dict[str, Any] = {
        "lane": world_obj.lane,
        "lane_label": world_obj.lane_label,
        "mask_by_pov": mask_by_pov,
        "total_nodes": len(nodes),
        "pov": pov_text,
        "pov_choice_count": len(pov_choices),
        "delta_keys": sorted(delta_payload.keys()),
    }
    if diff_summary:
        context["diff_summary"] = diff_summary

    response: Dict[str, Any] = {
        "world": world_obj.snapshot(),
        "suggestions": suggestions,
        "context": context,
    }
    if diff_payload:
        response["diff"] = diff_payload
    return response


@router.post("/diff")
async def diff_world(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    source_id = data.get("source") or data.get("world_a")
    target_id = data.get("target") or data.get("world_b")
    if not isinstance(source_id, str) or not source_id.strip():
        raise HTTPException(status_code=400, detail="source must be a non-empty string")
    if not isinstance(target_id, str) or not target_id.strip():
        raise HTTPException(status_code=400, detail="target must be a non-empty string")
    mask = data.get("mask_pov")
    mask_by_pov = True if mask is None else bool(mask)
    try:
        return diff_worlds(
            source_id.strip(),
            target_id.strip(),
            mask_by_pov=mask_by_pov,
        )
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/merge")
async def merge_world(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    source_id = data.get("source")
    target_id = data.get("target")
    if not isinstance(source_id, str) or not source_id.strip():
        raise HTTPException(status_code=400, detail="source must be a non-empty string")
    if not isinstance(target_id, str) or not target_id.strip():
        raise HTTPException(status_code=400, detail="target must be a non-empty string")
    try:
        result = merge_worlds(source_id.strip(), target_id.strip())
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result
