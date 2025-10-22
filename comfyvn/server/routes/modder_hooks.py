from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Sequence

from fastapi import APIRouter, Body, HTTPException, WebSocket, WebSocketDisconnect

from comfyvn.core import modder_hooks
from comfyvn.server.core import webhooks as webhook_core

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/modder", tags=["Modder Hooks"])
_WEBHOOK_ATTACHED = False


def _serialize_spec(spec) -> Dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "ws_topic": spec.ws_topic,
        "rest_event": spec.rest_event,
        "payload": spec.payload_fields,
    }


def _webhook_forwarder(event: str, payload: Dict[str, Any]) -> None:
    try:
        webhook_core.emit(event, payload)
    except Exception:
        LOGGER.debug("Modder webhook forward failed for %s", event, exc_info=True)


# Register webhook bridge once per process.
if not _WEBHOOK_ATTACHED:
    modder_hooks.register_listener(_webhook_forwarder)
    _WEBHOOK_ATTACHED = True


@router.get("/hooks")
def list_hooks() -> Dict[str, Any]:
    specs = [_serialize_spec(spec) for spec in modder_hooks.hook_specs().values()]
    webhooks_state = webhook_core.list_hooks()
    return {
        "ok": True,
        "hooks": specs,
        "webhooks": webhooks_state.get("items", []),
        "plugin_host": {
            "enabled": modder_hooks.plugin_host_enabled(),
            "root": modder_hooks.plugin_root(),
        },
        "history": modder_hooks.history(limit=15),
    }


@router.get("/hooks/history")
def history(limit: int = 25) -> Dict[str, Any]:
    return {"ok": True, "items": modder_hooks.history(limit)}


@router.post("/hooks/webhooks")
def register_webhook(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    event = str(payload.get("event") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not event or event not in modder_hooks.hook_specs():
        raise HTTPException(status_code=400, detail="unsupported event")
    if not url:
        raise HTTPException(status_code=400, detail="webhook url required")
    secret = payload.get("secret")
    if secret is not None:
        secret = str(secret)
    return webhook_core.put_hook(event, url, secret)


@router.delete("/hooks/webhooks")
def delete_webhook(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    event = str(payload.get("event") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not event or event not in modder_hooks.hook_specs():
        raise HTTPException(status_code=400, detail="unsupported event")
    if not url:
        raise HTTPException(status_code=400, detail="webhook url required")
    return webhook_core.delete_hook(event, url)


@router.post("/hooks/test")
def emit_test(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    event = str(payload.get("event") or "").strip()
    if not event:
        event = "on_scene_enter"
    if event not in modder_hooks.hook_specs():
        raise HTTPException(status_code=400, detail="unsupported event")
    data = payload.get("payload") or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")
    modder_hooks.emit(event, dict(data))
    return {"ok": True, "event": event}


async def _subscribe_ws(topics: Optional[Sequence[str]]) -> asyncio.Queue:
    try:
        return await modder_hooks.subscribe(topics)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.websocket("/hooks/ws")
async def ws_hooks(ws: WebSocket) -> None:
    await ws.accept()
    try:
        init = await ws.receive_json()
        topics = init.get("topics") if isinstance(init, dict) else None
        if topics is not None and not isinstance(topics, list):
            topics = None
    except Exception:
        topics = None
    try:
        queue = await _subscribe_ws(topics)
    except HTTPException as exc:
        await ws.send_json({"ok": False, "error": exc.detail})
        await ws.close()
        return
    await ws.send_json(
        {
            "ok": True,
            "subscribed": topics or list(modder_hooks.hook_specs().keys()),
        }
    )
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=20.0)
                await ws.send_json(item)
            except asyncio.TimeoutError:
                await ws.send_json({"ping": True})
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        modder_hooks.unsubscribe(queue)
        try:
            await ws.close()
        except Exception:
            pass
