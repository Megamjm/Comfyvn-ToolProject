from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

VariableType = Literal["string", "number", "boolean", "any"]
NodeType = Literal["line", "choice", "jump", "set", "end"]


class VariableSpec(BaseModel):
    type: VariableType = Field("any")
    default: Optional[Any] = None
    description: Optional[str] = None


class ConditionSpec(BaseModel):
    var: str = Field(..., min_length=1, max_length=64)
    equals: Optional[Any] = None
    not_equals: Optional[Any] = None
    exists: bool = True

    def evaluate(self, scope: Dict[str, Any]) -> bool:
        value = scope.get(self.var)
        if self.equals is not None and value != self.equals:
            return False
        if self.not_equals is not None and value == self.not_equals:
            return False
        if self.equals is None and self.not_equals is None and self.exists:
            return bool(value)
        return True


class ScenarioNodeBase(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    type: NodeType
    label: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class LineNode(ScenarioNodeBase):
    type: Literal["line"] = "line"
    text: str = Field(..., min_length=1)
    speaker: Optional[str] = Field(default=None, max_length=100)
    expression: Optional[str] = Field(default=None, max_length=100)
    next: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ChoiceOptionSpec(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1, max_length=300)
    next: str = Field(..., min_length=1, max_length=64)
    weight: float = Field(default=1.0, ge=0.0)
    conditions: List[ConditionSpec] = Field(default_factory=list)
    set: Dict[str, Any] = Field(default_factory=dict)


class ChoiceNode(ScenarioNodeBase):
    type: Literal["choice"] = "choice"
    prompt: Optional[str] = Field(default=None, max_length=300)
    choices: List[ChoiceOptionSpec] = Field(default_factory=list)


class JumpNode(ScenarioNodeBase):
    type: Literal["jump"] = "jump"
    next: str = Field(..., min_length=1, max_length=64)


class SetNode(ScenarioNodeBase):
    type: Literal["set"] = "set"
    assign: Dict[str, Any] = Field(default_factory=dict)
    next: Optional[str] = None


class EndNode(ScenarioNodeBase):
    type: Literal["end"] = "end"
    result: Optional[str] = Field(default=None, max_length=200)


ScenarioNode = Annotated[
    Union[LineNode, ChoiceNode, JumpNode, SetNode, EndNode],
    Field(discriminator="type"),
]


class ScenarioSpec(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    title: Optional[str] = Field(default=None, max_length=200)
    start: str = Field(..., min_length=1, max_length=64)
    nodes: List[ScenarioNode] = Field(default_factory=list)
    variables: Dict[str, VariableSpec] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _post_validate(self) -> "ScenarioSpec":
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"duplicate node id: {node.id}")
            seen.add(node.id)
        if self.start not in seen and self.nodes:
            raise ValueError(f"start references unknown node '{self.start}'")
        return self


def validate_scenario(doc: Dict[str, Any]) -> Dict[str, Any]:
    try:
        scenario = ScenarioSpec.model_validate(doc)
    except ValidationError as exc:
        return {"ok": False, "errors": exc.errors()}

    errors: List[Dict[str, Any]] = []
    node_ids: Dict[str, ScenarioNode] = {node.id: node for node in scenario.nodes}

    def _check_target(target: Optional[str], node: ScenarioNode, field: str) -> None:
        if target is None:
            return
        if target not in node_ids:
            errors.append(
                {
                    "msg": f"node '{node.id}' {field} references unknown node '{target}'",
                    "node": node.id,
                    "field": field,
                }
            )

    for node in scenario.nodes:
        if isinstance(node, LineNode):
            _check_target(node.next, node, "next")
        elif isinstance(node, JumpNode):
            _check_target(node.next, node, "next")
        elif isinstance(node, SetNode):
            _check_target(node.next, node, "next")
        elif isinstance(node, ChoiceNode):
            if not node.choices:
                errors.append(
                    {"msg": f"choice node '{node.id}' has no options", "node": node.id}
                )
            seen_choice: set[str] = set()
            for choice in node.choices:
                if choice.id in seen_choice:
                    errors.append(
                        {
                            "msg": f"choice node '{node.id}' has duplicate option '{choice.id}'",
                            "node": node.id,
                            "option": choice.id,
                        }
                    )
                seen_choice.add(choice.id)
                _check_target(choice.next, node, f"choice[{choice.id}].next")

    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "schema": ScenarioSpec.model_json_schema()}
