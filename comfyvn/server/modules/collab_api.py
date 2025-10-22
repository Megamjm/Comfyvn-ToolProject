from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Dict, Iterable, List, Sequence

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from comfyvn.collab import CRDTOperation
from comfyvn.core.modder_hooks import emit as emit_modder_hook
from comfyvn.server.core.collab import (
    HUB,
    CollabClientState,
    get_room,
    refresh_feature_flags,
)

try:  # Optional metrics integration
    from comfyvn.server.core.metrics import WS_CONN  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - optional dependency
    WS_CONN = None  # type: ignore

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collab", tags=["Collaboration"])


def _dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _actor_from_header(websocket: WebSocket) -> Dict[str, str]:
    """Extract actor information from headers; fall back to anon tokens."""
    name = websocket.headers.get("x-comfyvn-name") or "anon"
    user_id = websocket.headers.get("x-comfyvn-user") or f"anon:{secrets.token_hex(4)}"
    return {"user_id": user_id, "name": name}


def _parse_operations(
    raw_ops: Sequence[Dict[str, Any]], fallback_actor: str
) -> List[CRDTOperation]:
    operations: List[CRDTOperation] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            continue
        op_id = str(item.get("op_id") or f"{fallback_actor}:{secrets.token_hex(6)}")
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        payload = item.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        actor = str(item.get("actor") or fallback_actor)
        try:
            clock = int(item.get("clock") or 0)
        except Exception:
            clock = 0
        timestamp = item.get("timestamp")
        try:
            ts_value = float(timestamp) if timestamp is not None else time.time()
        except Exception:
            ts_value = time.time()
        operations.append(
            CRDTOperation(
                op_id=op_id,
                actor=actor,
                clock=clock,
                kind=kind,
                payload=payload,
                timestamp=ts_value,
            )
        )
    return operations


async def _send(state: CollabClientState, payload: Dict[str, Any]) -> None:
    message = _dumps(payload)
    await state.websocket.send_text(message)


async def _broadcast(
    room, payload: Dict[str, Any], *, exclude: Iterable[str] | None = None
) -> None:
    message = _dumps(payload)
    exclude_set = set(exclude or ())
    failures: List[str] = []
    for client_id, state in list(room.clients.items()):
        if client_id in exclude_set:
            continue
        try:
            await state.websocket.send_text(message)
        except Exception as exc:  # pragma: no cover - network path
            LOGGER.warning("Collab broadcast failed for %s: %s", client_id, exc)
            failures.append(client_id)
    for client_id in failures:
        room.leave(client_id)


async def _broadcast_presence(room) -> None:
    presence = room.presence().as_dict()
    await _broadcast(
        room,
        {
            "type": "presence.update",
            "scene_id": room.scene_id,
            "presence": presence,
        },
    )


async def _ensure_enabled() -> Dict[str, Any]:
    await refresh_feature_flags()
    flags = HUB._feature_flags  # type: ignore[attr-defined]
    if not flags.get("enable_collaboration", False):
        raise HTTPException(403, "collaboration_disabled")
    return flags


@router.websocket("/ws")
async def collab_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    flags = await _ensure_enabled()

    scene_id = (websocket.query_params.get("scene_id") or "").strip() or "default"
    actor = _actor_from_header(websocket)
    client_id = actor["user_id"]
    user_name = actor["name"] or "anon"

    room = await get_room(scene_id)
    state = CollabClientState(
        client_id=client_id,
        user_name=user_name,
        websocket=websocket,
    )
    room.join(state)
    try:
        if WS_CONN:
            WS_CONN.labels(scene=scene_id).inc()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - metrics optional
        pass

    try:
        await _send(
            state,
            {
                "type": "room.joined",
                "scene_id": scene_id,
                "actor": actor,
                "feature_flags": flags,
                "version": room.document.version,
                "clock": room.document.clock,
                "snapshot": room.document.snapshot(),
                "presence": room.presence().as_dict(),
            },
        )
        await _broadcast_presence(room)

        while True:
            raw = await websocket.receive_text()
            try:
                body = json.loads(raw)
            except Exception:
                body = {"type": "ping"}
            msg_type = str(body.get("type") or "").lower()

            if msg_type == "ping":
                await _send(state, {"type": "pong", "ts": time.time()})
                continue

            if msg_type == "presence.update":
                payload = body.get("payload") or {}
                if isinstance(payload, dict):
                    room.update_presence(client_id, payload)
                    await _broadcast_presence(room)
                continue

            if msg_type == "doc.pull":
                await _send(
                    state,
                    {
                        "type": "doc.snapshot",
                        "scene_id": scene_id,
                        "version": room.document.version,
                        "clock": room.document.clock,
                        "snapshot": room.document.snapshot(),
                    },
                )
                continue

            if msg_type == "doc.apply":
                ops_raw = body.get("operations") or []
                since = body.get("since")
                operations = _parse_operations(ops_raw, client_id)
                if not operations:
                    await _send(
                        state,
                        {
                            "type": "doc.update",
                            "scene_id": scene_id,
                            "version": room.document.version,
                            "clock": room.document.clock,
                            "operations": [],
                            "snapshot": room.document.snapshot(),
                        },
                    )
                    continue
                results = room.apply_operations(client_id, operations)
                changed = any(res.applied for res in results)
                payload: Dict[str, Any] = {
                    "type": "doc.update",
                    "scene_id": scene_id,
                    "version": room.document.version,
                    "clock": room.document.clock,
                    "operations": [res.as_dict() for res in results],
                }
                if changed or body.get("include_snapshot"):
                    payload["snapshot"] = room.document.snapshot()
                mod_payload = {
                    "scene_id": scene_id,
                    "version": room.document.version,
                    "clock": room.document.clock,
                    "operations": [op.as_dict() for op in operations],
                    "applied": [res.applied for res in results],
                    "actor": client_id,
                    "timestamp": time.time(),
                }
                if "snapshot" in payload:
                    mod_payload["snapshot"] = payload["snapshot"]
                if changed:
                    LOGGER.info(
                        "collab.op applied scene=%s version=%s ops=%s",
                        scene_id,
                        room.document.version,
                        [res.operation.op_id for res in results],
                    )
                emit_modder_hook("on_collab_operation", mod_payload)
                if isinstance(since, int) and since >= 0:
                    history = [
                        record.as_dict()
                        for record in room.document.operations_since(since)
                    ]
                    payload["history"] = history
                await _broadcast(room, payload)
                if room.dirty:
                    await room.flush()
                continue

            if msg_type == "control.request":
                ttl = body.get("ttl")
                try:
                    ttl_value = float(ttl) if ttl is not None else None
                except Exception:
                    ttl_value = None
                outcome = room.request_control(client_id, ttl=ttl_value)
                await _send(
                    state,
                    {
                        "type": "control.state",
                        "scene_id": scene_id,
                        "state": outcome,
                    },
                )
                await _broadcast_presence(room)
                continue

            if msg_type == "control.release":
                outcome = room.release_control(client_id)
                await _send(
                    state,
                    {
                        "type": "control.state",
                        "scene_id": scene_id,
                        "state": outcome,
                    },
                )
                await _broadcast_presence(room)
                continue

            if msg_type == "feature.refresh":
                await refresh_feature_flags()
                await _send(
                    state,
                    {
                        "type": "feature.flags",
                        "scene_id": scene_id,
                        "flags": HUB._feature_flags,  # type: ignore[attr-defined]
                    },
                )
                continue

            await _send(
                state,
                {
                    "type": "error",
                    "scene_id": scene_id,
                    "error": "unknown_message_type",
                    "received": msg_type,
                },
            )
    except WebSocketDisconnect:
        LOGGER.info(
            "Collab websocket disconnected for scene %s (%s)", scene_id, client_id
        )
    except Exception as exc:  # pragma: no cover - network path
        LOGGER.warning("Collab websocket error (%s): %s", client_id, exc, exc_info=True)
        try:
            await _send(
                state,
                {
                    "type": "error",
                    "scene_id": scene_id,
                    "error": "server_exception",
                    "detail": str(exc),
                },
            )
        except Exception:
            pass
    finally:
        room.leave(client_id)
        try:
            await room.flush()
        except Exception:
            LOGGER.debug("Collab flush failed on disconnect for scene %s", scene_id)
        try:
            if WS_CONN:
                WS_CONN.labels(scene=scene_id).dec()  # type: ignore[attr-defined]
        except Exception:
            pass
        await _broadcast_presence(room)
        HUB.discard_empty()


@router.get("/health")
async def collab_health() -> Dict[str, Any]:
    flags = await _ensure_enabled()
    stats = HUB.stats()
    return {"ok": True, "stats": stats, "feature_flags": flags}


@router.get("/presence/{scene_id}")
async def collab_presence(scene_id: str) -> Dict[str, Any]:
    await _ensure_enabled()
    room = await get_room(scene_id)
    return {
        "ok": True,
        "scene_id": scene_id,
        "version": room.document.version,
        "presence": room.presence().as_dict(),
    }


@router.get("/snapshot/{scene_id}")
async def collab_snapshot(scene_id: str) -> Dict[str, Any]:
    await _ensure_enabled()
    room = await get_room(scene_id)
    return {
        "ok": True,
        "scene_id": scene_id,
        "snapshot": room.document.snapshot(),
    }


@router.get("/history/{scene_id}")
async def collab_history(scene_id: str, since: int = 0) -> Dict[str, Any]:
    await _ensure_enabled()
    room = await get_room(scene_id)
    if since < 0:
        since = 0
    history = [record.as_dict() for record in room.document.operations_since(since)]
    return {
        "ok": True,
        "scene_id": scene_id,
        "since": since,
        "history": history,
        "version": room.document.version,
    }


@router.post("/flush")
async def collab_flush() -> Dict[str, Any]:
    await _ensure_enabled()
    await HUB.flush_all()
    return {"ok": True, "message": "collab state flushed"}
