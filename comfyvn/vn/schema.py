"""
Scenario schema models for the VN loader pipeline.

These Pydantic models normalise the authoring surface that modders provide
and which the Mini-VN player / Ren'Py exporter consumes.  They aim to be
permissive when reading input (allowing loose typing) while ensuring we
emit a predictable, well-formed structure on disk.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FieldValidationInfo,
    field_validator,
    model_validator,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _trim(value: Optional[str]) -> Optional[str]:
    return value.strip() if isinstance(value, str) else value


def _slugify(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    slug = value.strip().lower()
    slug = _SLUG_RE.sub("_", slug).strip("_")
    return slug or None


class PersonaRef(BaseModel):
    """Light-weight persona metadata that scenes reference."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    displayName: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    portraitRef: Optional[str] = None

    @field_validator("displayName", "portraitRef")
    @classmethod
    def _trim_strings(cls, value: Optional[str]) -> Optional[str]:
        return _trim(value)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalise_tags(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        tags: List[str] = []
        for item in value:
            if not item:
                continue
            tag = str(item).strip()
            if tag and tag not in tags:
                tags.append(tag)
        return tags

    @model_validator(mode="after")
    def _ensure_identity(self) -> "PersonaRef":
        if not self.displayName and self.id:
            self.displayName = self.id
        if not self.id and self.displayName:
            self.id = _slugify(self.displayName)
        return self


class Choice(BaseModel):
    """Branch option leaving a node."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    text: str
    to: Optional[str] = None
    when: Optional[str] = None
    weight: float = 1.0

    @field_validator("text", "to", "when")
    @classmethod
    def _trim_strings(cls, value: Optional[str]) -> Optional[str]:
        return _trim(value)

    @model_validator(mode="after")
    def _ensure_weight(self) -> "Choice":
        if self.weight is None:
            self.weight = 1.0
        else:
            self.weight = float(self.weight)
        return self


class Presentation(BaseModel):
    """Visual/audio presentation hints for a node."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    expression: Optional[str] = None
    pose: Optional[str] = None
    camera: Optional[Dict[str, float]] = None
    sfx: Optional[str] = None
    lut: Optional[str] = None

    @model_validator(mode="after")
    def _ensure_camera_numbers(self) -> "Presentation":
        if self.camera:
            self.camera = {k: float(v) for k, v in self.camera.items()}
        return self


class Anchor(BaseModel):
    """Timeline/bookmark reference within a scene."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    label: str
    ts: Optional[float] = None

    @field_validator("label")
    @classmethod
    def _trim_label(cls, value: str) -> str:
        return value.strip()


class Node(BaseModel):
    """Dialogue or narration beat."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    speaker: Optional[str] = None
    text: Optional[str] = None
    aside: Optional[str] = None
    choices: List[Choice] = Field(default_factory=list)
    presentation: Optional[Presentation] = None

    @field_validator("speaker", "text", "aside")
    @classmethod
    def _trim_strings(cls, value: Optional[str]) -> Optional[str]:
        return _trim(value)

    @model_validator(mode="after")
    def _ensure_choices(self) -> "Node":
        if not self.presentation:
            self.presentation = Presentation()
        return self


class Scene(BaseModel):
    """A self-contained conversation flow."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    title: Optional[str] = None
    order: int = 0
    cast: List[PersonaRef] = Field(default_factory=list)
    nodes: List[Node]
    anchors: List[Anchor] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _trim_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("cast", mode="before")
    @classmethod
    def _normalise_cast(cls, value: Any) -> List[Any]:
        if not value:
            return []
        normalised: List[Any] = []
        if isinstance(value, (str, dict)):
            value = [value]
        for item in value:
            if isinstance(item, str):
                normalised.append({"id": item, "displayName": item})
            elif isinstance(item, PersonaRef):
                normalised.append(item)
            else:
                normalised.append(item)
        return normalised

    @model_validator(mode="after")
    def _ensure_order(self) -> "Scene":
        if self.order is None:
            self.order = 0
        self.nodes = list(self.nodes or [])
        self.anchors = list(self.anchors or [])
        if not self.title:
            self.title = self.id or "Untitled Scene"
        return self


class AssetRef(BaseModel):
    """Asset binding metadata surfaced to modders."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    kind: str = "generic"
    uri: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ScenarioDocument(BaseModel):
    """Intermediate representation used by the loader."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    projectId: Optional[str] = None
    title: Optional[str] = None
    personas: List[PersonaRef] = Field(default_factory=list)
    scenes: List[Scene] = Field(default_factory=list)
    assets: List[AssetRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    sources: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("personas", "scenes", "assets", mode="before")
    @classmethod
    def _normalise_iterables(cls, value: Any, info: FieldValidationInfo) -> List[Any]:
        if not value:
            return []
        if info.field_name == "scenes" and isinstance(value, dict) and "nodes" in value:
            return [value]
        if info.field_name == "personas" and isinstance(value, (str, PersonaRef)):
            if isinstance(value, str):
                return [{"id": value, "displayName": value}]
            return [value]
        if info.field_name == "personas" and isinstance(value, list):
            normalised = []
            for item in value:
                if isinstance(item, str):
                    normalised.append({"id": item, "displayName": item})
                else:
                    normalised.append(item)
            return normalised
        if info.field_name == "assets" and isinstance(value, (str, AssetRef)):
            if isinstance(value, str):
                return [{"id": value, "kind": "generic"}]
            return [value]
        if info.field_name == "assets" and isinstance(value, list):
            normalised_assets = []
            for item in value:
                if isinstance(item, str):
                    normalised_assets.append({"id": item, "kind": "generic"})
                else:
                    normalised_assets.append(item)
            return normalised_assets
        if isinstance(value, (PersonaRef, Scene, AssetRef)):
            return [value]
        return value
