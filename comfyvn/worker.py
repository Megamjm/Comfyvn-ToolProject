from __future__ import annotations

import json
import os
import socket
import time
from typing import Any, Dict, List

import redis
from PySide6.QtGui import QAction

from comfyvn.ext.plugins import PluginManager
from comfyvn.modules.orchestration.pipeline_manager import (PipelineContext,
                                                            PipelineManager)
from comfyvn.plugins.echo import plugin as echo_plugin
from comfyvn.plugins.webhook import plugin as webhook_plugin
from comfyvn.server.core.redis_support import EVENTS, GROUP, STREAM, _r

VISIBILITY_TIMEOUT = float(os.getenv("VISIBILITY_TIMEOUT", "60"))
CONSUMER = os.getenv("WORKER_NAME", socket.gethostname())


def _emit(r: redis.Redis, kind: str, payload: Dict[str, Any]):
    r.xadd(EVENTS, {"event": json.dumps({"kind": kind, "payload": payload})})


def _deps_done(r: redis.Redis, rec: dict) -> bool:
    import json as _json

    deps = _json.loads(rec.get("depends_on", "[]") or "[]")
    for d in deps:
        st = r.hget(f"comfyvn:job:{d}", "status")
        if st != "done":
            return False
    return True


def _run_job(r: redis.Redis, jid: str):
    key = f"comfyvn:job:{jid}"
    rec = r.hgetall(key)
    if not rec:
        return
    if rec.get("status") == "canceled":
        _emit(r, "job:canceled", {"id": jid, "phase": "pre"})
        return
    if not _deps_done(r, rec):
        time.sleep(0.5)
        r.xadd(STREAM, {"id": jid})
        return

    typ = rec.get("type")
    payload = json.loads(rec.get("payload", "{}"))
    attempt = int(rec.get("attempt", "0")) + 1
    retries = int(rec.get("retries", "0"))
    r.hset(key, mapping={"status": "running", "attempt": str(attempt)})
    _emit(r, "job:start", {"id": jid, "type": typ, "attempt": attempt})

    plugins = PluginManager()
    plugins.register(echo_plugin)
    plugins.register(webhook_plugin)

    def on_event(k, d):
        _emit(r, k, d)

    ctx = PipelineContext(on_event=on_event)
    pm = PipelineManager(ctx)

    try:
        if typ == "render":
            out = pm.render_character_with_progress(payload, jid)
        elif typ == "batch":
            items = (payload or {}).get("items") or []
            results = []
            n = max(1, len(items))
            for i, it in enumerate(items):
                _emit(r, "job:progress", {"id": jid, "p": i / n})
                rid = it.get("id") or f"{jid[:8]}_{i+1}"
                it = {**it, "id": rid}
                res = pm.render_character_with_progress(it, jid)
                results.append(res)
                _emit(r, "job:progress", {"id": jid, "p": (i + 1) / n})
            ok = all(x.get("ok") for x in results) if results else False
            out = {"ok": ok, "results": results}
        else:
            out = plugins.handle(typ, payload, jid)

        if out.get("ok"):
            r.hset(key, mapping={"status": "done", "result": json.dumps(out)})
            _emit(r, "job:done", {"id": jid, "ok": True})
        else:
            if attempt <= retries:
                r.hset(
                    key,
                    mapping={"status": "queued", "error": out.get("error", "unknown")},
                )
                r.xadd(STREAM, {"id": jid})
                _emit(r, "job:requeued", {"id": jid, "reason": "retry"})
            else:
                r.hset(
                    key,
                    mapping={"status": "error", "error": out.get("error", "unknown")},
                )
                _emit(r, "job:done", {"id": jid, "ok": False})
    except Exception as e:
        if attempt <= retries:
            r.hset(key, mapping={"status": "queued", "error": str(e)})
            r.xadd(STREAM, {"id": jid})
            _emit(r, "job:requeued", {"id": jid, "reason": "exception"})
        else:
            r.hset(key, mapping={"status": "error", "error": str(e)})
            _emit(r, "job:done", {"id": jid, "ok": False})


def main():
    r = _r()
    try:
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    last_idle_check = time.time()
    while True:
        # reclaim
        if time.time() - last_idle_check > 5.0:
            try:
                pend = r.xpending_range(
                    STREAM,
                    GROUP,
                    min="-",
                    max="+",
                    count=50,
                    consumername=None,
                    idle=int(VISIBILITY_TIMEOUT * 1000),
                )
                for p in pend:
                    try:
                        r.xclaim(
                            STREAM,
                            GROUP,
                            CONSUMER,
                            min_idle_time=int(VISIBILITY_TIMEOUT * 1000),
                            message_ids=[p["message_id"]],
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            last_idle_check = time.time()

        try:
            resp = r.xreadgroup(
                GROUP, CONSUMER, streams={STREAM: ">"}, count=10, block=2000
            )
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
                continue
            resp = []
        if not resp:
            continue
        for _s, msgs in resp:
            for mid, fields in msgs:
                jid = fields.get("id")
                if not jid:
                    try:
                        r.xack(STREAM, GROUP, mid)
                    except Exception:
                        pass
                    continue
                _run_job(r, jid)
                try:
                    r.xack(STREAM, GROUP, mid)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
