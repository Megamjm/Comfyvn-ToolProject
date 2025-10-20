from __future__ import annotations
from PySide6.QtGui import QAction
from typing import Dict, Any
from .models import WorkflowSpec

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "single_echo": {
        "name": "single_echo",
        "version": 1,
        "inputs": {
            "message": {"type": "string", "required": True, "description": "Message to echo"}
        },
        "outputs": {"result": "echo.out"},
        "nodes": [
            {
                "id": "echo",
                "type": "echo",
                "label": "Echo Job",
                "params": {"message": "${message}"},
                "inputs": {},
                "outputs": {"out": "$output.result"}
            }
        ],
        "edges": []
    },
    "two_step": {
        "name": "two_step",
        "version": 1,
        "inputs": {"first": {"type":"string"}, "second": {"type":"string"}},
        "outputs": {"combined": "concat.out"},
        "nodes": [
            {"id": "echo1", "type": "echo", "params": {"message": "${first}"}, "inputs": {}, "outputs": {}},
            {"id": "echo2", "type": "echo", "params": {"message": "${second}"}, "inputs": {}, "outputs": {}},
            {"id": "concat", "type": "concat", "params": {"a": "${first}", "b": "${second}"}, "inputs": {}, "outputs": {"out":"$output.combined"}},
        ],
        "edges": []
    }
}

def list_templates(): return [{"name": k, "description": t.get("meta",{}).get("description","")} for k,t in TEMPLATES.items()]

def get_template(name: str) -> Dict[str, Any]: return TEMPLATES[name]

def instantiate(name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    import json as _json, re
    raw = _json.loads(_json.dumps(TEMPLATES[name]))  # deep copy
    pattern = re.compile(r"\$\{([a-zA-Z0-9_]+)\}")
    def sub(val):
        if isinstance(val, str):
            def repl(m):
                key = m.group(1)
                return str(params.get(key, ""))
            return pattern.sub(repl, val)
        if isinstance(val, dict): return {k: sub(v) for k,v in val.items()}
        if isinstance(val, list): return [sub(v) for v in val]
        return val
    return sub(raw)