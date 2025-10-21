from __future__ import annotations

import json
import secrets
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from PySide6.QtGui import QAction

from comfyvn.server.core.collab import HUB, Client
from comfyvn.server.core.storage import scene_load, scene_save

router = APIRouter()


def actor_from_header(websocket: WebSocket) -> dict:
    # simple anon fallback
    return {"user_id": "anon:" + secrets.token_hex(4), "name": "anon"}


@router.websocket("/ws")
async def ws(websocket: WebSocket):
    scene_id = (websocket.query_params.get("scene_id") or "").strip() or "default"
    await websocket.accept()
    actor = actor_from_header(websocket)
    cid = actor["user_id"]
    client = Client(ws=websocket, user_id=cid, user_name=actor["name"] or "anon")
    HUB.join(scene_id, client)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "presence",
                    "scene_id": scene_id,
                    "data": HUB.presence(scene_id),
                }
            )
        )
        while True:
            msg = await websocket.receive_text()
            try:
                body = json.loads(msg)
            except Exception:
                body = {"type": "ping"}
            typ = body.get("type")
            if typ == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif typ == "presence":
                await websocket.send_text(
                    json.dumps({"type": "presence", "data": HUB.presence(scene_id)})
                )
            elif typ == "lock.acquire":
                ok = HUB.acquire_lock(scene_id, cid, body.get("ttl"))
                await websocket.send_text(
                    json.dumps(
                        {"type": "lock", "ok": ok, "data": HUB.presence(scene_id)}
                    )
                )
            elif typ == "lock.release":
                ok = HUB.release_lock(scene_id, cid)
                await websocket.send_text(
                    json.dumps(
                        {"type": "lock", "ok": ok, "data": HUB.presence(scene_id)}
                    )
                )
            elif typ == "patch":
                base = int(body.get("base_version") or 0)
                sc = scene_load(scene_id)
                try:
                    sc2 = dict(sc)
                    sc2["scene_id"] = scene_id
                    if body.get("title") is not None:
                        sc2["title"] = body.get("title")
                    if isinstance(body.get("lines"), list):
                        sc2["lines"] = body.get("lines")
                    scene_save(sc2, expected_version=base)
                    payload = {
                        "type": "applied",
                        "scene_id": scene_id,
                        "version": sc2.get("version"),
                        "scene": sc2,
                    }
                    for uid, c in list(HUB.rooms.get(scene_id, {}).items()):
                        try:
                            await c.ws.send_text(json.dumps(payload))
                        except Exception:
                            pass
                except Exception as e:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "conflict",
                                "scene_id": scene_id,
                                "error": str(e),
                                "latest": sc,
                            }
                        )
                    )
            else:
                await websocket.send_text(json.dumps({"type": "unknown"}))
    except WebSocketDisconnect:
        HUB.leave(scene_id, cid)
        # final presence broadcast best effort
        try:
            payload = {
                "type": "presence",
                "scene_id": scene_id,
                "data": HUB.presence(scene_id),
            }
            for uid, c in list(HUB.rooms.get(scene_id, {}).items()):
                await c.ws.send_text(json.dumps(payload))
        except Exception:
            pass


@router.get("/presence")
async def presence(scene_id: str):
    return {"ok": True, "presence": HUB.presence(scene_id)}


@router.get("/scene/version/{scene_id}")
async def scene_version(scene_id: str):
    sc = scene_load(scene_id)
    return {"ok": True, "version": int(sc.get("version") or 0)}
