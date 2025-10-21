from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from comfyvn.assets.pose_utils import load_pose as _load_pose
from comfyvn.ext.plugins import PluginManager
from comfyvn.workflows.models import NodeSpec, WorkflowSpec

CACHE_DIR = Path("./data/runtime_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _hash(o: Any) -> str:
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _interpolate(val: Any, ctx: Dict[str, Any]) -> Any:
    # Replace ${var} with ctx[var]; supports nested: ${a.b}
    import re as _re

    if isinstance(val, str):
        pat = _re.compile(r"\$\{([a-zA-Z0-9_\.]+)\}")

        def repl(m):
            key = m.group(1)
            cur: Any = ctx
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return ""
            return str(cur)

        return pat.sub(repl, val)
    if isinstance(val, dict):
        return {k: _interpolate(v, ctx) for k, v in val.items()}
    if isinstance(val, list):
        return [_interpolate(v, ctx) for v in val]
    return val


@dataclass
class NodeResult:
    outputs: Dict[str, Any] = field(default_factory=dict)
    started: float = 0.0
    finished: float = 0.0
    cached: bool = False
    ok: bool = True
    error: Optional[str] = None


@dataclass
class RunRecord:
    id: str
    name: str
    inputs: Dict[str, Any]
    started: float
    finished: float = 0.0
    ok: bool = False
    nodes: Dict[str, NodeResult] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)


class NodeExec:
    def __init__(self):
        self.pm = PluginManager()

    def call(self, typ: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        low = typ.lower()
        if low == "echo":
            return {"ok": True, "out": str(payload.get("message", ""))}
        if low == "concat":
            a, b = str(payload.get("a", "")), str(payload.get("b", ""))
            return {"ok": True, "out": a + b}
        if low == "loadimage":
            filename = payload.get("filename")
            return {"ok": True, "image": filename if filename else None}
        if low == "compositeimage":
            layers = payload.get("layers")
            if isinstance(layers, str):
                layer_list = [
                    part.strip() for part in layers.split(",") if part.strip()
                ]
            else:
                layer_list = [layer for layer in list(layers or []) if layer]
            return {
                "ok": True,
                "out": f"composite:{payload.get('background')}:{':'.join(layer_list)}",
                "layers": layer_list,
            }
        if low == "loadpose":
            filename = payload.get("filename")
            try:
                pose = _load_pose(filename) if filename else {}
            except Exception:
                pose = {"pose_id": (Path(filename).stem if filename else "pose")}
            return {"ok": True, "pose": json.dumps(pose)}
        if low == "posedelta":
            pose_a_json = payload.get("pose_a") or payload.get("pose_a_json")
            pose_b_json = payload.get("pose_b") or payload.get("pose_b_json")
            try:
                pose_a = (
                    json.loads(pose_a_json)
                    if isinstance(pose_a_json, str)
                    else pose_a_json or {}
                )
                pose_b = (
                    json.loads(pose_b_json)
                    if isinstance(pose_b_json, str)
                    else pose_b_json or {}
                )
            except Exception:
                pose_a, pose_b = {}, {}
            skeleton_a = pose_a.get("skeleton", {}) if isinstance(pose_a, dict) else {}
            skeleton_b = pose_b.get("skeleton", {}) if isinstance(pose_b, dict) else {}
            delta = {"deltas": {}}
            for key, coords in skeleton_a.items():
                other = skeleton_b.get(key) or {}
                delta["deltas"][key] = {
                    "dx": (other.get("x", 0) or 0) - (coords.get("x", 0) or 0),
                    "dy": (other.get("y", 0) or 0) - (coords.get("y", 0) or 0),
                }
            return {"ok": True, "delta": json.dumps(delta), "out": json.dumps(delta)}
        if low == "poseinterpolator":
            pose_json = payload.get("pose_a_json")
            delta_json = payload.get("delta_json")
            try:
                pose = (
                    json.loads(pose_json)
                    if isinstance(pose_json, str)
                    else pose_json or {}
                )
                delta = (
                    json.loads(delta_json)
                    if isinstance(delta_json, str)
                    else delta_json or {}
                )
            except Exception:
                pose, delta = {}, {}
            t = float(payload.get("t", 1.0))
            skeleton = pose.get("skeleton", {}) if isinstance(pose, dict) else {}
            deltas = delta.get("deltas", {}) if isinstance(delta, dict) else {}
            blended = {
                "pose_id": f"{pose.get('pose_id', 'pose')}__interp",
                "skeleton": {},
            }
            for key, coords in skeleton.items():
                base_x = coords.get("x", 0) or 0
                base_y = coords.get("y", 0) or 0
                d = deltas.get(key, {})
                blended["skeleton"][key] = {
                    "x": base_x + (d.get("dx", 0) or 0) * t,
                    "y": base_y + (d.get("dy", 0) or 0) * t,
                }
            return {"ok": True, "pose": json.dumps(blended)}
        if low == "poseinterpolatorworkflow":
            inner = {
                "name": "pose_blend_inline",
                "inputs": {},
                "outputs": {"pose": "interp.pose"},
                "nodes": [
                    {
                        "id": "load_a",
                        "type": "LoadPose",
                        "params": {"filename": payload.get("pose_a")},
                        "inputs": {},
                        "outputs": {"pose": "load_a.pose"},
                    },
                    {
                        "id": "load_b",
                        "type": "LoadPose",
                        "params": {"filename": payload.get("pose_b")},
                        "inputs": {},
                        "outputs": {"pose": "load_b.pose"},
                    },
                    {
                        "id": "delta",
                        "type": "PoseDelta",
                        "params": {},
                        "inputs": {"pose_a": "load_a.pose", "pose_b": "load_b.pose"},
                        "outputs": {"delta": "delta.out"},
                    },
                    {
                        "id": "interp",
                        "type": "PoseInterpolator",
                        "params": {"t": payload.get("blend", 0.5)},
                        "inputs": {
                            "pose_a_json": "load_a.pose",
                            "delta_json": "delta.out",
                        },
                        "outputs": {"pose": "$output.pose"},
                    },
                ],
                "edges": [],
            }
            runtime = WorkflowRuntime(inner, run_id=f"pose_{int(time.time()*1000)}")
            result = runtime.run()
            return {"ok": True, "pose": result.get("outputs", {}).get("pose")}
        # Fallback: plugin job
        res = self.pm.handle(typ, payload, None) or {}
        # adapt common fields
        if "out" not in res:
            if "output" in res:
                res["out"] = res["output"]
            else:
                # pick first non-ok field
                for k, v in res.items():
                    if k != "ok":
                        res["out"] = v
                        break
        return res


class WorkflowRuntime:
    def __init__(
        self,
        wf: Dict[str, Any],
        run_id: str,
        inputs: Dict[str, Any] | None = None,
        cache: bool = True,
    ):
        self.spec = WorkflowSpec.model_validate(wf)
        self.inputs = inputs or {}
        self.exec = NodeExec()
        self.cache_enabled = cache
        self.run_id = run_id
        self.values: Dict[str, Dict[str, Any]] = {}  # node -> outputs
        self.ctx = {"input": self.inputs, **self.inputs}

    def _node_deps(self, n: NodeSpec) -> Set[str]:
        deps: Set[str] = set()
        for src in list(n.inputs.values()):
            if src and "." in src and not src.startswith("$input."):
                snode, _ = src.split(".", 1)
                deps.add(snode)
        return deps

    def _toposort(self) -> List[str]:
        ids = {n.id: self._node_deps(n) for n in self.spec.nodes}
        out: List[str] = []
        while ids:
            ready = [k for k, v in list(ids.items()) if not v]
            if not ready:  # cycle
                raise ValueError("cycle detected in workflow")
            for r in ready:
                out.append(r)
                ids.pop(r)
            for v in ids.values():
                v.difference_update(set(ready))
        return out

    def _cache_key(self, n: NodeSpec, payload: Dict[str, Any]) -> str:
        base = {"id": n.id, "type": n.type, "payload": payload}
        return _hash(base)

    def _read_cache(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.cache_enabled:
            return None
        p = CACHE_DIR / f"{key}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _write_cache(self, key: str, out: Dict[str, Any]):
        if not self.cache_enabled:
            return
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(out), encoding="utf-8")

    def _eval_inputs(self, n: NodeSpec) -> Dict[str, Any]:
        def resolve(src):
            if isinstance(src, list):
                return [resolve(item) for item in src if item]
            if not src:
                return None
            if isinstance(src, str) and "|" in src and not src.startswith("$input."):
                parts = [part.strip() for part in src.split("|") if part.strip()]
                return [resolve(part) for part in parts]
            if isinstance(src, str) and src.startswith("$input."):
                key = src.split(".", 1)[1]
                return self.inputs.get(key)
            if isinstance(src, str) and "." in src:
                snode, sport = src.split(".", 1)
                if snode not in self.values:
                    raise ValueError(
                        f"node '{snode}' has not produced outputs for '{src}'"
                    )
                node_outputs = self.values[snode]
                if sport not in node_outputs:
                    raise ValueError(
                        f"node '{snode}' missing output '{sport}' for '{src}'"
                    )
                return node_outputs[sport]
            return src

        out: Dict[str, Any] = {}
        for port, src in (n.inputs or {}).items():
            out[port] = resolve(src)
        return out

    def _coerce_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # simple interpolation only
        return _interpolate(params, self.ctx)

    def run(self) -> Dict[str, Any]:
        order = self._toposort()
        record: Dict[str, Any] = {}
        for nid in order:
            node = next(n for n in self.spec.nodes if n.id == nid)
            # optional conditional: when=false skips
            when = (
                node.params.get("when", True) if isinstance(node.params, dict) else True
            )
            if isinstance(when, str):
                when = bool(_interpolate(when, self.ctx))
            if not when:
                self.values[nid] = {}
                continue
            payload = {
                **self._coerce_params(node.params or {}),
                **self._eval_inputs(node),
            }
            key = self._cache_key(node, payload)
            cached = self._read_cache(key)
            ns = NodeResult(started=time.time())
            if cached is not None:
                ns.outputs = cached
                ns.finished = time.time()
                ns.cached = True
                self.values[nid] = cached
            else:
                res = self.exec.call(node.type, payload) or {}
                ok = bool(res.get("ok", True))
                ns.ok = ok
                if not ok:
                    ns.error = str(res.get("error", "error"))
                    ns.finished = time.time()
                    record[nid] = ns
                    break
                outs = {k: v for k, v in res.items() if k not in {"ok"}}
                ns.outputs = outs
                ns.finished = time.time()
                self._write_cache(key, outs)
                self.values[nid] = outs
            record[nid] = ns
            # expose node.outputs -> $output
            for port, target in (node.outputs or {}).items():
                if target.startswith("$output."):
                    oname = target.split(".", 1)[1]
                    self.ctx[oname] = self.values[nid].get(port)
        # build final outputs from wf.outputs
        outputs: Dict[str, Any] = {}
        for name, ref in (self.spec.outputs or {}).items():
            if "." in ref:
                n, p = ref.split(".", 1)
                outputs[name] = self.values.get(n, {}).get(p)
        return {
            "ok": True,
            "outputs": outputs,
            "nodes": {k: vars(v) for k, v in record.items()},
        }
