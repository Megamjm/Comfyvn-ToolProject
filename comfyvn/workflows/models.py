from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from PySide6.QtGui import QAction

ParamType = Literal["string", "number", "boolean", "image", "asset", "any"]


class ParamSpec(BaseModel):
    type: ParamType = Field("string")
    required: bool = Field(default=True)
    default: Optional[Any] = None
    description: Optional[str] = None


class NodeSpec(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=64)
    label: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    inputs: Dict[str, str] = Field(
        default_factory=dict
    )  # port -> source "node.port" or "$input.name"
    outputs: Dict[str, str] = Field(
        default_factory=dict
    )  # port -> "$output.name" to expose


class EdgeSpec(BaseModel):
    from_node: str
    from_port: str
    to_node: str
    to_port: str


class WorkflowSpec(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version: int = 1
    inputs: Dict[str, ParamSpec] = Field(default_factory=dict)
    outputs: Dict[str, str] = Field(default_factory=dict)  # name -> "node.port"
    nodes: List[NodeSpec] = Field(default_factory=list)
    edges: List[EdgeSpec] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("nodes")
    @classmethod
    def unique_node_ids(cls, nodes: List[NodeSpec]):
        ids = set()
        for n in nodes:
            if n.id in ids:
                raise ValueError(f"duplicate node id: {n.id}")
            ids.add(n.id)
        return nodes


def validate_workflow(doc: Dict[str, Any]) -> Dict[str, Any]:
    try:
        wf = WorkflowSpec.model_validate(doc)
    except ValidationError as e:
        return {"ok": False, "errors": e.errors()}

    # Graph checks: inputs point to existing nodes or $input
    node_ids = {n.id for n in wf.nodes}
    for n in wf.nodes:
        for port, src in n.inputs.items():
            if src.startswith("$input."):
                name = src.split(".", 1)[1]
                if name not in wf.inputs:
                    return {
                        "ok": False,
                        "errors": [
                            {"msg": f"missing input '{name}' for node {n.id}.{port}"}
                        ],
                    }
            else:
                if "." not in src:
                    return {
                        "ok": False,
                        "errors": [{"msg": f"bad source '{src}' for {n.id}.{port}"}],
                    }
                snode, sport = src.split(".", 1)
                if snode not in node_ids:
                    return {
                        "ok": False,
                        "errors": [
                            {"msg": f"unknown source node '{snode}' for {n.id}.{port}"}
                        ],
                    }
        # outputs: ok to expose as $output but ensure names unique
        for port, target in n.outputs.items():
            if not target.startswith("$output."):
                return {
                    "ok": False,
                    "errors": [
                        {
                            "msg": f"output mapping must start with $output., got {target}"
                        }
                    ],
                }

    # Check wf.outputs map to node.port
    for name, ref in wf.outputs.items():
        if "." not in ref:
            return {
                "ok": False,
                "errors": [
                    {"msg": f"workflow output '{name}' must reference node.port"}
                ],
            }
        sn, sp = ref.split(".", 1)
        if sn not in node_ids:
            return {
                "ok": False,
                "errors": [
                    {"msg": f"workflow output '{name}' references unknown node '{sn}'"}
                ],
            }

    return {"ok": True, "schema": WorkflowSpec.model_json_schema()}
