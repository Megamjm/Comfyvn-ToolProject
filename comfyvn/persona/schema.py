from __future__ import annotations

import re
import time
from copy import deepcopy
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
)

from pydantic import BaseModel, ConfigDict, Field, validator

__all__ = [
    "PersonaValidationError",
    "PersonaPronouns",
    "PersonaTagSet",
    "PersonaPaletteSwatch",
    "PersonaPalette",
    "PersonaAppearance",
    "PersonaLore",
    "PersonaRelationship",
    "PersonaVoice",
    "PersonaPreferences",
    "PersonaNSFW",
    "PersonaSourceRef",
    "PersonaProfile",
    "normalise_tags",
    "merge_tag_sets",
    "build_persona_record",
    "apply_nsfw_policy",
    "summarise_persona",
    "slugify",
]

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
DEFAULT_STAGE_ANCHORS: Dict[str, Any] = {
    "stage": {
        "primary": "center",
        "positions": {
            "left": {"x": -300, "y": 0},
            "center": {"x": 0, "y": 0},
            "right": {"x": 300, "y": 0},
            "offscreen": {"x": 9999, "y": 9999},
        },
    }
}

DEFAULT_PALETTE = [
    {"name": "primary", "hex": "#a855f7"},
    {"name": "secondary", "hex": "#6366f1"},
    {"name": "accent", "hex": "#ec4899"},
]

ALLOWED_ROLES = {"player", "npc", "support", "companion"}


class PersonaValidationError(ValueError):
    """Raised when persona payloads fail schema validation."""


def slugify(value: Any, *, default: str = "persona") -> str:
    text = str(value or "").strip().lower()
    slug = _SLUG_RE.sub("-", text).strip("-")
    return slug or default


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalise_tags(value: Any) -> List[str]:
    """Normalise tag payloads into a deduplicated, lowercase list."""
    if value is None:
        return []
    tags: List[str] = []
    if isinstance(value, str):
        chunks = re.split(r"[,\|;]", value)
        tags = [chunk.strip().lower() for chunk in chunks if chunk.strip()]
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if not item:
                continue
            text = str(item).strip().lower()
            if text:
                tags.append(text)
    else:
        text = str(value).strip().lower()
        if text:
            tags.append(text)
    seen: set[str] = set()
    deduped: List[str] = []
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped


def _normalise_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [chunk.strip() for chunk in re.split(r"[,\n;]", value)]
        return [chunk for chunk in parts if chunk]
    if isinstance(value, (list, tuple, set)):
        entries: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                entries.append(text)
        return entries
    text = str(value or "").strip()
    return [text] if text else []


class PersonaPronouns(BaseModel):
    subject: str = Field(default="they")
    object: str = Field(default="them")
    possessive: str = Field(default="their")
    reflexive: str = Field(default="themselves")

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @validator("subject", "object", "possessive", "reflexive", pre=True)
    def _default(cls, value: Any, field):  # type: ignore[override]
        text = str(value or "").strip().lower()
        if not text:
            defaults = {
                "subject": "they",
                "object": "them",
                "possessive": "their",
                "reflexive": "themselves",
            }
            return defaults[field.alias or field.name]
        return text


class PersonaTagSet(BaseModel):
    general: List[str] = Field(default_factory=list)
    style: List[str] = Field(default_factory=list)
    nsfw: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @validator("general", "style", "nsfw", pre=True)
    def _prepare(cls, value: Any):  # type: ignore[override]
        return normalise_tags(value)

    @validator("general", "style", "nsfw")
    def _dedupe(cls, value: List[str]):  # type: ignore[override]
        seen: set[str] = set()
        normalised: List[str] = []
        for tag in value:
            canonical = tag.lower()
            if canonical in seen:
                continue
            seen.add(canonical)
            normalised.append(canonical)
        return normalised


class PersonaPaletteSwatch(BaseModel):
    name: str = Field(default="swatch")
    hex: str = Field(default="#777777")
    notes: Optional[str] = None

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @validator("name", pre=True)
    def _name(cls, value: Any):  # type: ignore[override]
        text = str(value or "").strip()
        return text or "swatch"

    @validator("hex", pre=True)
    def _hex(cls, value: Any):  # type: ignore[override]
        text = str(value or "").strip().lower()
        match = _COLOR_RE.search(text)
        return match.group(0) if match else "#777777"


class PersonaPalette(BaseModel):
    primary: Optional[str] = None
    secondary: Optional[str] = None
    accent: Optional[str] = None
    swatches: List[PersonaPaletteSwatch] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @validator("primary", "secondary", "accent", pre=True)
    def _color(cls, value: Any):  # type: ignore[override]
        if not value:
            return None
        text = str(value).strip()
        match = _COLOR_RE.search(text)
        return match.group(0) if match else None

    @validator("swatches", mode="before")
    def _swatches(cls, value: Any):  # type: ignore[override]
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]


class PersonaAppearance(BaseModel):
    summary: Optional[str] = None
    traits: List[str] = Field(default_factory=list)
    notable_features: List[str] = Field(default_factory=list)
    height: Optional[str] = None
    physique: Optional[str] = None
    style: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @validator("traits", "notable_features", "style", pre=True)
    def _list(cls, value: Any):  # type: ignore[override]
        return _normalise_list(value)


class PersonaLore(BaseModel):
    backstory: Optional[str] = None
    motivation: Optional[str] = None
    hooks: List[str] = Field(default_factory=list)
    quotes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @validator("hooks", "quotes", pre=True)
    def _list(cls, value: Any):  # type: ignore[override]
        return _normalise_list(value)


class PersonaRelationship(BaseModel):
    name: str = Field(default="unknown")
    relation: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @validator("name", pre=True)
    def _name(cls, value: Any):  # type: ignore[override]
        text = str(value or "").strip()
        return text or "unknown"

    @validator("tags", pre=True)
    def _tags(cls, value: Any):  # type: ignore[override]
        return normalise_tags(value)


class PersonaVoice(BaseModel):
    style: Optional[str] = None
    tone: Optional[str] = None
    accent: Optional[str] = None
    reference: Optional[str] = None
    hints: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @validator("hints", pre=True)
    def _list(cls, value: Any):  # type: ignore[override]
        return _normalise_list(value)


class PersonaPreferences(BaseModel):
    likes: List[str] = Field(default_factory=list)
    dislikes: List[str] = Field(default_factory=list)
    nope: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @validator("likes", "dislikes", "nope", pre=True)
    def _prepare(cls, value: Any):  # type: ignore[override]
        return _normalise_list(value)


class PersonaNSFW(BaseModel):
    allowed: bool = Field(default=False)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @validator("tags", pre=True)
    def _tags(cls, value: Any):  # type: ignore[override]
        return normalise_tags(value)


class PersonaSourceRef(BaseModel):
    type: str = Field(default="manual")
    value: Optional[str] = None
    attribution: Optional[str] = None
    rights: Optional[str] = None
    hash: Optional[str] = None

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @validator("type", pre=True)
    def _type(cls, value: Any):  # type: ignore[override]
        text = str(value or "").strip().lower()
        return text or "manual"


class PersonaProfile(BaseModel):
    id: str
    name: str
    summary: Optional[str] = None
    role: str = Field(default="npc")
    pronouns: PersonaPronouns = Field(default_factory=PersonaPronouns)
    species: List[str] = Field(default_factory=list)
    tags: PersonaTagSet = Field(default_factory=PersonaTagSet)
    appearance: PersonaAppearance = Field(default_factory=PersonaAppearance)
    palette: PersonaPalette = Field(default_factory=PersonaPalette)
    lore: PersonaLore = Field(default_factory=PersonaLore)
    relationships: List[PersonaRelationship] = Field(default_factory=list)
    voice: PersonaVoice = Field(default_factory=PersonaVoice)
    preferences: PersonaPreferences = Field(default_factory=PersonaPreferences)
    nsfw: PersonaNSFW = Field(default_factory=PersonaNSFW)
    anchors: Dict[str, Any] = Field(
        default_factory=lambda: deepcopy(DEFAULT_STAGE_ANCHORS)
    )
    sources: List[PersonaSourceRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=lambda: time.time())
    updated_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @validator("role", pre=True)
    def _role(cls, value: Any):  # type: ignore[override]
        text = str(value or "").strip().lower()
        if text not in ALLOWED_ROLES:
            return "npc"
        return text

    @validator("species", pre=True)
    def _species(cls, value: Any):  # type: ignore[override]
        if value is None:
            return []
        if isinstance(value, str):
            entries = [
                chunk.strip() for chunk in re.split(r"[,\n]", value) if chunk.strip()
            ]
        elif isinstance(value, (list, tuple, set)):
            entries = [str(item).strip() for item in value if str(item).strip()]
        else:
            entries = [str(value).strip()]
        return [entry for entry in entries if entry]

    @validator("relationships", pre=True)
    def _relationships(cls, value: Any):  # type: ignore[override]
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @validator("anchors", pre=True)
    def _anchors(cls, value: Any):  # type: ignore[override]
        if not isinstance(value, dict):
            return deepcopy(DEFAULT_STAGE_ANCHORS)
        if "stage" not in value:
            value = dict(value)
            value["stage"] = deepcopy(DEFAULT_STAGE_ANCHORS["stage"])
        return value


def merge_tag_sets(*sets: Mapping[str, Sequence[str]]) -> PersonaTagSet:
    merged: Dict[str, List[str]] = {"general": [], "style": [], "nsfw": []}
    for tag_set in sets:
        for key in ("general", "style", "nsfw"):
            if key not in tag_set:
                continue
            merged[key].extend(normalise_tags(tag_set[key]))
    return PersonaTagSet(**merged)


def _ensure_palette(payload: MutableMapping[str, Any]) -> None:
    palette = payload.setdefault("palette", {})
    swatches = palette.get("swatches") or []
    if not swatches:
        palette["swatches"] = list(DEFAULT_PALETTE)
    if not palette.get("primary"):
        palette["primary"] = palette["swatches"][0]["hex"]
    if not palette.get("secondary") and len(palette["swatches"]) > 1:
        palette["secondary"] = palette["swatches"][1]["hex"]
    if not palette.get("accent") and len(palette["swatches"]) > 2:
        palette["accent"] = palette["swatches"][2]["hex"]


def _ensure_tag_sets(payload: MutableMapping[str, Any]) -> None:
    tags = payload.setdefault("tags", {})
    payload["tags"] = PersonaTagSet(**tags).model_dump()


def _ensure_anchors(payload: MutableMapping[str, Any]) -> None:
    anchors = payload.get("anchors")
    if not isinstance(anchors, dict) or "stage" not in anchors:
        payload["anchors"] = deepcopy(DEFAULT_STAGE_ANCHORS)


def _prepare_sources(payload: MutableMapping[str, Any]) -> None:
    sources = payload.get("sources")
    if sources is None:
        payload["sources"] = []
        return
    prepared: List[Dict[str, Any]] = []
    for entry in sources:
        if not isinstance(entry, Mapping):
            continue
        spec = PersonaSourceRef(**entry)
        prepared.append(spec.model_dump())
    payload["sources"] = prepared


def apply_nsfw_policy(
    persona: Mapping[str, Any], *, allow_nsfw: bool
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    trimmed = {
        "nsfw_tags_removed": [],
        "nsfw_notes_removed": False,
        "general_tags_removed": [],
    }
    record = deepcopy(dict(persona))
    nsfw_block = record.get("nsfw") or {}
    if allow_nsfw:
        record["nsfw"] = PersonaNSFW(**nsfw_block).model_dump()
        record["nsfw"]["allowed"] = True
        return record, trimmed

    nsfw_tags = normalise_tags(nsfw_block.get("tags"))
    trimmed["nsfw_tags_removed"] = nsfw_tags
    trimmed["nsfw_notes_removed"] = bool(nsfw_block.get("notes"))

    tag_set = record.get("tags") or {}
    general = normalise_tags(tag_set.get("general"))
    remaining_general = [tag for tag in general if tag not in nsfw_tags]
    trimmed["general_tags_removed"] = [
        tag for tag in general if tag not in remaining_general
    ]

    tag_set["general"] = remaining_general
    tag_set.setdefault("nsfw", [])
    record["tags"] = PersonaTagSet(**tag_set).model_dump()
    record["nsfw"] = {"allowed": False, "tags": [], "notes": None}
    return record, trimmed


def build_persona_record(
    payload: Mapping[str, Any],
    *,
    allow_nsfw: bool = False,
    default_role: str = "npc",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise PersonaValidationError("Persona payload must be a mapping.")

    data = dict(payload)
    name = _clean_text(data.get("name"))
    if not name:
        raise PersonaValidationError("Persona name is required.")

    persona_id = data.get("id") or slugify(data.get("id") or data.get("slug") or name)
    data["id"] = slugify(persona_id)
    data["name"] = name
    data.setdefault("summary", data.get("summary") or data.get("blurb"))
    data.setdefault("role", data.get("role") or default_role)
    data.setdefault("created_at", data.get("created_at") or time.time())
    data.setdefault("updated_at", data.get("updated_at") or data["created_at"])

    _ensure_palette(data)
    _ensure_tag_sets(data)
    _ensure_anchors(data)
    _prepare_sources(data)

    try:
        persona = PersonaProfile(**data)
    except Exception as exc:  # pragma: no cover - defensive
        raise PersonaValidationError(str(exc)) from exc

    record = persona.model_dump()
    filtered, trimmed = apply_nsfw_policy(record, allow_nsfw=allow_nsfw)
    return filtered, trimmed


def summarise_persona(persona: Mapping[str, Any]) -> Dict[str, Any]:
    tags = persona.get("tags") or {}
    voice = persona.get("voice") or {}
    pronouns = persona.get("pronouns") or {}
    return {
        "id": persona.get("id"),
        "name": persona.get("name"),
        "summary": persona.get("summary"),
        "role": persona.get("role"),
        "species": persona.get("species") or [],
        "pronouns": {
            key: pronouns.get(key) for key in ("subject", "object", "possessive")
        },
        "tags": {
            "general": tags.get("general") or [],
            "style": tags.get("style") or [],
        },
        "voice": {
            "style": voice.get("style"),
            "tone": voice.get("tone"),
            "accent": voice.get("accent"),
        },
    }
