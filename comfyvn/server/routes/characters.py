from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

from comfyvn.assets.character_manager import CharacterManager, _slugify
from comfyvn.bridge.comfy_hardening import (
    HardenedBridgeError,
    HardenedBridgeUnavailable,
    HardenedComfyBridge,
)
from comfyvn.studio.core import AssetRegistry

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/api/characters", tags=["Characters"])

_manager = CharacterManager()
_asset_registry = AssetRegistry()
_bridge = HardenedComfyBridge()

_UNSET = object()
_VALID_RENDER_KINDS = {"portrait", "fullbody"}


def _normalise_tags(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace("|", ",").replace(";", ",").split(",")
        return [chunk.strip() for chunk in parts if chunk.strip()]
    if isinstance(value, (list, set, tuple)):
        tags: List[str] = []
        for entry in value:
            if entry is None:
                continue
            chunk = str(entry).strip()
            if chunk:
                tags.append(chunk)
        return tags
    return []


def _normalise_loras(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = value.get("loras")
    if not isinstance(value, list):
        return []
    entries: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("name") or "").strip()
        if not path:
            continue
        entry: Dict[str, Any] = {"path": path}
        weight = item.get("weight", item.get("strength"))
        if weight is not None:
            try:
                entry["weight"] = float(weight)
            except (TypeError, ValueError):
                LOGGER.debug("Ignoring invalid LoRA weight for %s", path)
        clip = item.get("clip")
        if clip is not None:
            try:
                entry["clip"] = float(clip)
            except (TypeError, ValueError):
                LOGGER.debug("Ignoring invalid LoRA clip for %s", path)
        if item.get("source"):
            entry["source"] = str(item["source"])
        entries.append(entry)
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for entry in entries:
        if entry["path"] in seen:
            continue
        seen.add(entry["path"])
        deduped.append(entry)
    return deduped


def _normalise_kind(value: Any) -> str:
    text = str(value or "portrait").strip().lower()
    if text == "potrait":  # legacy typo handling
        text = "portrait"
    if text not in _VALID_RENDER_KINDS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported render kind '{value}'"
        )
    return text


def _resolve_character(reference: Optional[str]) -> tuple[str, Dict[str, Any]]:
    if not reference:
        raise HTTPException(status_code=400, detail="Character reference required.")
    resolved = _manager.resolve_character(str(reference))
    if not resolved:
        raise HTTPException(
            status_code=404, detail=f"Character '{reference}' not found."
        )
    return resolved


@router.get("")
def list_characters():
    items = _manager.list_characters()
    return {"ok": True, "data": {"items": items, "count": len(items)}}


@router.get("/{character_id}")
def get_character(character_id: str):
    record = _manager.get_character(character_id)
    if not record:
        raise HTTPException(status_code=404, detail="Character not found.")
    return {"ok": True, "data": record}


@router.post("/save")
def save_character(payload: Dict[str, Any] = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Character name is required.")

    raw_id = payload.get("id") or payload.get("character_id")
    character_id = _slugify(raw_id or name)

    tags = _normalise_tags(payload.get("tags"))
    pose = payload.get("pose") or payload.get("default_pose")
    expression = payload.get("expression") or payload.get("default_expression")
    notes = payload.get("notes")

    meta_payload = payload.get("meta", {})
    metadata: Dict[str, Any] = {}
    if isinstance(meta_payload, dict):
        metadata = dict(meta_payload)
    elif isinstance(meta_payload, str):
        stripped = meta_payload.strip()
        if stripped:
            try:
                metadata = json.loads(stripped)
            except Exception:
                notes = stripped

    loras_raw = payload.get("loras", _UNSET)
    loras = _normalise_loras(payload.get("loras")) if loras_raw is not _UNSET else None

    record_payload: Dict[str, Any] = {
        "name": name,
        "tags": tags,
        "pose": pose,
        "expression": expression,
        "meta": metadata,
    }
    if notes:
        record_payload["notes"] = notes
    if payload.get("avatars") is not None:
        record_payload["avatars"] = payload.get("avatars")
    if loras_raw is not _UNSET:
        record_payload["loras"] = loras or []

    record = _manager.register_character(character_id, record_payload)
    if loras_raw is not _UNSET:
        _manager.set_loras(character_id, loras or [])
        record["loras"] = loras or []
    return {"ok": True, "data": record}


@router.post("/render")
def render_character(payload: Dict[str, Any] = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")

    reference = payload.get("id") or payload.get("character_id") or payload.get("name")
    character_id, record = _resolve_character(reference)
    kind = _normalise_kind(payload.get("kind") or payload.get("mode"))

    _bridge.reload()
    if not _bridge.enabled:
        raise HTTPException(
            status_code=503,
            detail="ComfyUI hardened bridge is disabled in the current configuration.",
        )

    pose = payload.get("pose") or record.get("pose")
    expression = payload.get("expression") or record.get("expression")

    request_payload: Dict[str, Any] = {
        "character": character_id,
        "workflow_id": f"character.{kind}",
        "inputs": {"character": character_id},
        "metadata": {
            "character": {
                "id": character_id,
                "name": record.get("name"),
                "tags": record.get("tags"),
            },
            "render": {
                "kind": kind,
                "requested_at": time.time(),
            },
        },
    }
    if pose:
        request_payload["inputs"]["pose"] = pose
        request_payload["metadata"]["render"]["pose"] = pose
    if expression:
        request_payload["inputs"]["expression"] = expression
        request_payload["metadata"]["render"]["expression"] = expression
    if payload.get("prompt"):
        request_payload["prompt"] = payload["prompt"]
    if payload.get("seed") is not None:
        request_payload["seed"] = payload["seed"]
    overrides = payload.get("overrides")
    if overrides and isinstance(overrides, dict):
        request_payload["overrides"] = overrides

    try:
        result = _bridge.submit(request_payload)
    except HardenedBridgeUnavailable as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except HardenedBridgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Unexpected Comfy bridge error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    primary = result.get("primary_artifact") or {}
    primary_path = primary.get("path")
    if not primary_path:
        raise HTTPException(
            status_code=502, detail="Render did not produce an artifact."
        )

    source_path = Path(primary_path)
    if not source_path.exists():
        raise HTTPException(
            status_code=502, detail=f"Render artifact missing from disk: {source_path}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest_relative = (
        Path("characters") / character_id / kind / f"{timestamp}_{source_path.name}"
    )
    asset_type = f"character.{kind}"
    metadata = {
        "source": "character_designer",
        "character": {
            "id": character_id,
            "name": record.get("name"),
            "tags": record.get("tags"),
        },
        "render": {
            "kind": kind,
            "workflow_id": result.get("workflow_id"),
            "prompt_id": result.get("prompt_id"),
            "pose": pose,
            "expression": expression,
        },
        "comfyui": {
            "primary": primary,
            "sidecar": result.get("sidecar"),
        },
    }
    provenance = {
        "source": "comfyui.hardened_bridge",
        "character_id": character_id,
        "render_kind": kind,
        "workflow_id": result.get("workflow_id"),
        "prompt_id": result.get("prompt_id"),
        "inputs": request_payload.get("inputs"),
        "overrides": result.get("overrides"),
    }

    asset_info = _asset_registry.register_file(
        source_path,
        asset_type=asset_type,
        dest_relative=dest_relative,
        metadata=metadata,
        provenance=provenance,
        copy=True,
    )

    avatars = list(record.get("avatars") or [])
    avatar_entry = {
        "uid": asset_info.get("uid"),
        "path": asset_info.get("path"),
        "type": asset_type,
        "kind": kind,
        "created_at": time.time(),
    }
    existing_uids = {entry.get("uid") for entry in avatars if isinstance(entry, dict)}
    if avatar_entry["uid"] and avatar_entry["uid"] not in existing_uids:
        avatars.append(avatar_entry)

    updated_record = _manager.update_character(
        character_id,
        {
            "avatars": avatars,
            "last_render": {
                "uid": asset_info.get("uid"),
                "path": asset_info.get("path"),
                "kind": kind,
                "created_at": avatar_entry["created_at"],
            },
        },
    )

    return {
        "ok": True,
        "data": {
            "asset": asset_info,
            "character": updated_record,
            "bridge": {
                "prompt_id": result.get("prompt_id"),
                "workflow_id": result.get("workflow_id"),
                "sidecar": result.get("sidecar"),
            },
        },
    }
