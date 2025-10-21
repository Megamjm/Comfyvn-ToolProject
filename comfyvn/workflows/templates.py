from __future__ import annotations

from typing import Any, Dict

from PySide6.QtGui import QAction

from .models import WorkflowSpec

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "single_echo": {
        "name": "single_echo",
        "version": 1,
        "inputs": {
            "message": {
                "type": "string",
                "required": True,
                "description": "Message to echo",
            }
        },
        "outputs": {"result": "echo.out"},
        "nodes": [
            {
                "id": "echo",
                "type": "echo",
                "label": "Echo Job",
                "params": {"message": "${message}"},
                "inputs": {},
                "outputs": {"out": "$output.result"},
            }
        ],
        "edges": [],
    },
    "two_step": {
        "name": "two_step",
        "version": 1,
        "inputs": {"first": {"type": "string"}, "second": {"type": "string"}},
        "outputs": {"combined": "concat.out"},
        "nodes": [
            {
                "id": "echo1",
                "type": "echo",
                "params": {"message": "${first}"},
                "inputs": {},
                "outputs": {},
            },
            {
                "id": "echo2",
                "type": "echo",
                "params": {"message": "${second}"},
                "inputs": {},
                "outputs": {},
            },
            {
                "id": "concat",
                "type": "concat",
                "params": {"a": "${first}", "b": "${second}"},
                "inputs": {},
                "outputs": {"out": "$output.combined"},
            },
        ],
        "edges": [],
    },
    "sprite_composite_basic": {
        "name": "sprite_composite_basic",
        "version": 1,
        "meta": {
            "description": "Load a background and up to three sprite layers, returning a composited image."
        },
        "inputs": {
            "background": {"type": "string", "required": True},
            "sprite_left": {"type": "string", "required": False},
            "sprite_center": {"type": "string", "required": False},
            "sprite_right": {"type": "string", "required": False},
        },
        "outputs": {"image": "composite.out"},
        "nodes": [
            {
                "id": "bg",
                "type": "LoadImage",
                "params": {"filename": "${background}"},
                "inputs": {},
                "outputs": {"image": "bg.image"},
            },
            {
                "id": "left",
                "type": "LoadImage",
                "params": {"filename": "${sprite_left}"},
                "inputs": {},
                "outputs": {"image": "left.image"},
            },
            {
                "id": "center",
                "type": "LoadImage",
                "params": {"filename": "${sprite_center}"},
                "inputs": {},
                "outputs": {"image": "center.image"},
            },
            {
                "id": "right",
                "type": "LoadImage",
                "params": {"filename": "${sprite_right}"},
                "inputs": {},
                "outputs": {"image": "right.image"},
            },
            {
                "id": "composite",
                "type": "CompositeImage",
                "params": {},
                "inputs": {
                    "background": "bg.image",
                    "layers": "left.image|center.image|right.image",
                },
                "outputs": {"out": "$output.image"},
            },
        ],
        "edges": [],
    },
    "pose_blend_basic": {
        "name": "pose_blend_basic",
        "version": 1,
        "meta": {
            "description": "Blend between two pose JSON files using the ComfyUI PoseInterpolator node."
        },
        "inputs": {
            "pose_a": {"type": "string", "required": True},
            "pose_b": {"type": "string", "required": True},
            "blend": {"type": "float", "default": 0.5},
        },
        "outputs": {"pose": "interp.pose"},
        "nodes": [
            {
                "id": "load_a",
                "type": "LoadPose",
                "params": {"filename": "${pose_a}"},
                "inputs": {},
                "outputs": {"pose": "load_a.pose"},
            },
            {
                "id": "load_b",
                "type": "LoadPose",
                "params": {"filename": "${pose_b}"},
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
                "params": {"t": "${blend}"},
                "inputs": {"pose_a_json": "load_a.pose", "delta_json": "delta.out"},
                "outputs": {"pose": "$output.pose"},
            },
        ],
        "edges": [],
    },
    "sprite_pose_composite": {
        "name": "sprite_pose_composite",
        "version": 1,
        "meta": {
            "description": "Blend poses, then composite sprites with optional pose metadata embedded."
        },
        "inputs": {
            "background": {"type": "string", "required": True},
            "sprite": {"type": "string", "required": True},
            "pose_a": {"type": "string", "required": True},
            "pose_b": {"type": "string", "required": True},
            "blend": {"type": "float", "default": 0.5},
        },
        "outputs": {"image": "compose.out", "pose": "pose_interp.pose"},
        "nodes": [
            {
                "id": "pose_interp",
                "type": "PoseInterpolatorWorkflow",
                "params": {
                    "pose_a": "${pose_a}",
                    "pose_b": "${pose_b}",
                    "blend": "${blend}",
                },
                "inputs": {},
                "outputs": {"pose": "pose_interp.pose"},
            },
            {
                "id": "bg2",
                "type": "LoadImage",
                "params": {"filename": "${background}"},
                "inputs": {},
                "outputs": {"image": "bg2.image"},
            },
            {
                "id": "sprite",
                "type": "LoadImage",
                "params": {"filename": "${sprite}"},
                "inputs": {},
                "outputs": {"image": "sprite.image"},
            },
            {
                "id": "compose",
                "type": "CompositeImage",
                "params": {},
                "inputs": {"background": "bg2.image", "layers": "sprite.image"},
                "outputs": {"out": "$output.image"},
            },
        ],
        "edges": [],
    },
}


def list_templates():
    return [
        {"name": k, "description": t.get("meta", {}).get("description", "")}
        for k, t in TEMPLATES.items()
    ]


def get_template(name: str) -> Dict[str, Any]:
    return TEMPLATES[name]


def instantiate(name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    import json as _json
    import re

    raw = _json.loads(_json.dumps(TEMPLATES[name]))  # deep copy
    pattern = re.compile(r"\$\{([a-zA-Z0-9_]+)\}")

    def sub(val):
        if isinstance(val, str):

            def repl(m):
                key = m.group(1)
                return str(params.get(key, ""))

            return pattern.sub(repl, val)
        if isinstance(val, dict):
            return {k: sub(v) for k, v in val.items()}
        if isinstance(val, list):
            return [sub(v) for v in val]
        return val

    return sub(raw)
