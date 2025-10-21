from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from PySide6.QtGui import QAction

from comfyvn.ext.plugins import Plugin
from comfyvn.workflows.runtime import WorkflowRuntime

RUNS_DIR = Path("./data/runs")
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _write_run(rid: str, data: Dict[str, Any]):
    (RUNS_DIR / f"{rid}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def wf_run(payload: dict, job_id: str | None):
    wf = payload.get("workflow")
    name = payload.get("name") or (wf.get("name") if isinstance(wf, dict) else "run")
    if not wf and payload.get("name"):
        p = Path("./data/workflows") / f"{payload['name']}.json"
        wf = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        name = payload["name"]

    inputs = payload.get("inputs") or {}
    run_id = job_id or uuid.uuid4().hex[:12]
    rr: Dict[str, Any] = {
        "id": run_id,
        "name": name,
        "started": time.time(),
        "inputs": inputs,
        "ok": False,
        "outputs": {},
        "nodes": {},
        "resume_from": payload.get("resume_from") or "",
    }

    # Optional resume
    prev = None
    if payload.get("resume_from"):
        try:
            rp = RUNS_DIR / f"{payload['resume_from']}.json"
            if rp.exists():
                prev = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    try:
        rt = WorkflowRuntime(
            wf, run_id, inputs=inputs, cache=bool(payload.get("cache", True))
        )
        # prime cache with previous node outputs if resuming
        if prev and isinstance(prev.get("nodes"), dict):
            for nid, nd in prev["nodes"].items():
                outs = (nd or {}).get("outputs") or {}
                if outs:
                    try:
                        rt.values[nid] = outs
                    except Exception:
                        pass
        out = rt.run()
        rr["ok"] = bool(out.get("ok", True))
        rr["outputs"] = out.get("outputs", {})
        rr["nodes"] = out.get("nodes", {})
    except Exception as e:
        rr["ok"] = False
        rr["error"] = str(e)

    rr["finished"] = time.time()
    _write_run(run_id, rr)
    return {
        "ok": rr["ok"],
        "run_id": run_id,
        "outputs": rr.get("outputs"),
        "error": rr.get("error"),
    }


plugin = Plugin(
    name="wf_runtime",
    jobs={"wf_run": wf_run},
    meta={
        "builtin": True,
        "desc": "Execute workflows with optional resume and caching",
    },
)
