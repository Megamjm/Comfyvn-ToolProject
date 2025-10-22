from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.bridge.st_bridge.extension_sync import (
    collect_extension_status,
    resolve_paths,
    sync_extension,
)
from comfyvn.bridge.st_bridge.health import probe_health
from comfyvn.bridge.st_bridge.session_sync import (
    SessionSyncError,
    build_session_context,
    sync_session,
)
from comfyvn.core.scene_store import SceneStore
from comfyvn.core.world_loader import WorldLoader
from comfyvn.importers.silly_persona import (
    SillyPersonaImporter,
    import_chat_scenes,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/st", tags=["SillyTavern Bridge"])

_world_loader = WorldLoader()
_persona_manager = PersonaManager()
_scene_store = SceneStore()
_persona_importer = SillyPersonaImporter(_persona_manager)


class ExtensionSyncRequest(BaseModel):
    dry_run: bool = True
    source: Optional[str] = None
    destination: Optional[str] = None
    extension_name: str = "ComfyVN"


class ImportRequest(BaseModel):
    type: str
    data: Any = {}


class SessionSyncRequest(BaseModel):
    session_id: Optional[str] = None
    scene_id: Optional[str] = None
    node_id: Optional[str] = None
    pov: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    messages: list[Dict[str, Any]] = Field(default_factory=list)
    history: Optional[list[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    scene: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    base_url: Optional[str] = None
    plugin_base: Optional[str] = None
    timeout: float = Field(default=2.0, ge=0.1, le=30.0)
    dry_run: bool = False
    limit_messages: int = Field(
        default=50,
        ge=0,
        description="Trim chat transcripts to this many trailing entries (0 = unlimited).",
    )

    model_config = ConfigDict(extra="ignore")


def _iter_world_entries(payload: Any) -> Iterator[Tuple[str, Dict[str, Any]]]:
    if payload is None:
        return
    if isinstance(payload, dict):
        if "worlds" in payload:
            yield from _iter_world_entries(payload["worlds"])
            return
        if all(isinstance(v, dict) for v in payload.values()):
            for name, data in payload.items():
                yield name, dict(data or {})
            return
        name = str(payload.get("name") or payload.get("id") or "")
        yield name, dict(payload)
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("id") or "")
                content = (
                    item.get("data") if isinstance(item.get("data"), dict) else item
                )
                yield name, dict(content or {})


def _iter_character_payloads(payload: Any) -> Iterator[Dict[str, Any]]:
    if payload is None:
        return
    if isinstance(payload, dict):
        if "characters" in payload:
            yield from _iter_character_payloads(payload["characters"])
            return
        if all(isinstance(v, dict) for v in payload.values()):
            for _, data in payload.items():
                yield dict(data or {})
            return
        if isinstance(payload, dict):
            yield dict(payload)
            return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield dict(item)


def _sanitize_world_name(name: str, index: int) -> str:
    base = Path(name).stem if name else ""
    if not base:
        base = f"silly_world_{index}"
    return base


def _coerce_panel_reply(reply: Any) -> Optional[Dict[str, Any]]:
    if reply is None:
        return None
    if isinstance(reply, str):
        return {"role": "assistant", "content": reply}
    if isinstance(reply, dict):
        content = reply.get("content") or reply.get("text") or ""
        role = reply.get("role") or reply.get("speaker") or "assistant"
        panel: Dict[str, Any] = {
            "role": str(role or "assistant"),
            "content": str(content or ""),
        }
        if "emotion" in reply:
            panel["emotion"] = reply["emotion"]
        meta = reply.get("meta")
        if isinstance(meta, dict):
            panel["meta"] = dict(meta)
        return panel
    return {"role": "assistant", "content": str(reply)}


@router.get("/health", summary="SillyTavern bridge health status")
async def bridge_health(
    base_url: Optional[str] = Query(
        None, description="Override SillyTavern base URL for this probe."
    ),
    plugin_base: Optional[str] = Query(
        None, description="Override comfyvn-data-exporter plugin path."
    ),
    timeout: float = Query(3.0, description="HTTP timeout in seconds."),
) -> dict[str, object]:
    """Return SillyTavern availability plus extension path diagnostics."""
    return probe_health(base_url=base_url, plugin_base=plugin_base, timeout=timeout)


@router.get("/paths", summary="Resolve SillyTavern extension paths")
async def bridge_paths() -> dict[str, object]:
    """Resolve and return the SillyTavern extension source/destination paths."""
    paths = resolve_paths()
    payload = paths.as_dict()
    payload["sync"] = collect_extension_status(paths=paths)
    return payload


@router.post(
    "/extension/sync",
    summary="Sync the bundled SillyTavern extension into the target install.",
)
async def extension_sync_endpoint(request: ExtensionSyncRequest) -> dict[str, Any]:
    try:
        paths = resolve_paths(
            source=request.source,
            destination=request.destination,
            extension_name=request.extension_name,
        )
        result = sync_extension(
            source=request.source,
            destination=request.destination,
            extension_name=request.extension_name,
            dry_run=request.dry_run,
            paths=paths,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not request.dry_run:
        paths = resolve_paths(
            source=request.source,
            destination=request.destination,
            extension_name=request.extension_name,
        )

    result["paths"] = paths.as_dict()
    result["extension"] = collect_extension_status(paths=paths)
    return result


@router.post(
    "/session/sync",
    summary="Push VN session context to SillyTavern and return any reply payload.",
)
async def session_sync_endpoint(request: SessionSyncRequest) -> dict[str, Any]:
    """Bridge the current VN session state with the comfyvn-data-exporter plugin."""
    scene_payload = request.scene
    scene_source = "inline" if scene_payload is not None else "unspecified"
    if scene_payload is None and request.scene_id:
        scene_path = _scene_store.root / f"{request.scene_id}.json"
        if scene_path.exists():
            scene_payload = _scene_store.load(request.scene_id)
            scene_source = "store"
        else:
            scene_source = "missing"

    message_payload: list[Dict[str, Any]] = []
    if request.messages:
        message_payload = request.messages
    elif request.history:
        message_payload = request.history

    limit = request.limit_messages if request.limit_messages else None
    context = build_session_context(
        session_id=request.session_id,
        scene_id=request.scene_id,
        node_id=request.node_id,
        pov=request.pov,
        variables=request.variables,
        messages=message_payload,
        metadata=request.metadata,
        scene=scene_payload,
        user_id=request.user_id,
        limit_messages=limit,
    )

    try:
        result = sync_session(
            context,
            base_url=request.base_url,
            plugin_base=request.plugin_base,
            timeout=request.timeout,
            dry_run=request.dry_run,
        )
    except SessionSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = result.as_dict()
    payload["message_count"] = len(context.messages)
    payload["context"] = context.as_payload()
    payload["scene_source"] = scene_source
    payload["timeout"] = request.timeout
    payload["dry_run"] = request.dry_run
    panel_reply = _coerce_panel_reply(result.reply)
    payload["panel_reply"] = panel_reply
    payload["reply_text"] = panel_reply["content"] if panel_reply else None
    return payload


def _import_worlds(payload: Any) -> dict[str, Any]:
    entries = []
    errors = []
    for idx, (name, data) in enumerate(_iter_world_entries(payload), start=1):
        if not isinstance(data, dict) or not data:
            errors.append({"name": name, "error": "empty payload"})
            continue
        try:
            filename = _world_loader.save_world(_sanitize_world_name(name, idx), data)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to import world %s: %s", name or "<unnamed>", exc)
            errors.append({"name": name, "error": str(exc)})
            continue
        entries.append({"name": name or filename, "filename": filename})
    status = "ok" if entries else "empty"
    return {
        "status": status,
        "imported": len(entries),
        "worlds": entries,
        "errors": errors,
    }


def _import_characters(payload: Any) -> dict[str, Any]:
    manager = _persona_manager.character_manager
    entries = []
    errors = []
    for record in _iter_character_payloads(payload):
        try:
            imported = manager.import_character(record, overwrite=True)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(
                {"id": record.get("id") or record.get("name"), "error": str(exc)}
            )
            continue
        entries.append(imported)
    status = "ok" if entries else "empty"
    return {
        "status": status,
        "imported": len(entries),
        "characters": entries,
        "errors": errors,
    }


@router.post("/import", summary="Import SillyTavern assets via REST payloads.")
async def import_from_st(request: ImportRequest = Body(...)) -> dict[str, Any]:
    """Handle incoming data from the SillyTavern extension or plugins."""
    kind = (request.type or "").strip().lower()
    if kind in {"world", "worlds"}:
        result = _import_worlds(request.data)
        result["type"] = "worlds"
        return result
    if kind in {"persona", "personas"}:
        outcome = _persona_importer.import_many(request.data)
        outcome["type"] = "personas"
        return outcome
    if kind in {"chat", "chats"}:
        scenes = import_chat_scenes(_scene_store, request.data)
        scenes["type"] = "chats"
        return scenes
    if kind in {"character", "characters"}:
        result = _import_characters(request.data)
        result["type"] = "characters"
        return result
    if kind in {"active", "state"}:
        data = request.data or {}
        active_world = data.get("active_world")
        if active_world:
            _world_loader.active_world = active_world
        return {"status": "ok", "type": "active", "active_world": active_world}
    raise HTTPException(
        status_code=400, detail=f"Unsupported import type '{request.type}'"
    )


@router.options("/import", summary="CORS preflight handler for SillyTavern imports")
async def import_options() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.headers["Allow"] = "OPTIONS, POST"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response
