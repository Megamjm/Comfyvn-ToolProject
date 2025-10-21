"""
Directive schema definitions and compilation helpers for presentation planning.

`compile_plan(scene_state, node)` resolves a scene node plus live scene state into
an ordered list of atomic directives that downstream renderers or previews can
consume without additional normalization.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Channels supported by the presentation planner. The order of this enumeration
# is not relied upon; CHANNEL_ORDER defines the scheduling order explicitly.


class DirectiveChannel(str, Enum):
    PORTRAIT = "portrait"
    EXPRESSION = "expression"
    POSE = "pose"
    CAMERA = "camera"
    TWEEN = "tween"
    TIMING = "timing"
    SFX = "sfx"


CHANNEL_ORDER: tuple[DirectiveChannel, ...] = (
    DirectiveChannel.TIMING,
    DirectiveChannel.CAMERA,
    DirectiveChannel.PORTRAIT,
    DirectiveChannel.EXPRESSION,
    DirectiveChannel.POSE,
    DirectiveChannel.TWEEN,
    DirectiveChannel.SFX,
)


class AtomicDirective(BaseModel):
    """Single actionable directive emitted by the planner."""

    channel: DirectiveChannel
    action: str
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore", frozen=True)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "channel": self.channel.value,
            "action": self.action,
        }
        if self.target:
            data["target"] = self.target
        if self.payload:
            data["payload"] = _sorted_payload(self.payload)
        return data


class CharacterState(BaseModel):
    """State snapshot for a character currently on stage."""

    id: str
    display_name: str | None = None
    slot: str = "center"
    portrait: str | dict[str, Any] | None = None
    default_expression: str | None = None
    default_pose: str | None = None
    tween_preset: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class CameraState(BaseModel):
    """Default framing for the active scene."""

    shot: str | None = None
    angle: str | None = None
    focus: str | None = None
    movement: str | None = None
    duration: float | None = None
    easing: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class TimingState(BaseModel):
    """Default timing envelope for node presentation."""

    enter: float = 0.0
    hold: float = 2.5
    exit: float = 0.0
    easing: str = "linear"
    preset: str | None = None

    model_config = ConfigDict(extra="ignore")


class SceneState(BaseModel):
    """Aggregate presentation state for the scene at the current node."""

    scene_id: str
    characters: list[CharacterState] = Field(default_factory=list)
    camera: CameraState | None = None
    timing: TimingState | None = None
    ambient_sfx: list[str | dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class NodeDirectives(BaseModel):
    """Directive overrides declared on a node."""

    portrait: str | dict[str, Any] | None = None
    expression: str | dict[str, Any] | None = None
    pose: str | dict[str, Any] | None = None
    camera: str | dict[str, Any] | None = None
    tween: list[str | dict[str, Any]] = Field(default_factory=list)
    timing: str | dict[str, Any] | None = None
    sfx: list[str | dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class PresentationNode(BaseModel):
    """Minimal node contract needed to derive directives."""

    id: str
    type: str = "text"
    speaker: str | None = None
    directives: NodeDirectives = Field(default_factory=NodeDirectives)
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


def compile_plan(
    scene_state: SceneState, node: PresentationNode
) -> list[dict[str, Any]]:
    """
    Resolve the presentation plan for a scene node.

    Returns a deterministic list of atomic directive dictionaries ordered by
    CHANNEL_ORDER. Payload keys are sorted to provide a stable JSON shape.
    """

    char_map = {c.id: c for c in scene_state.characters}
    speaker_id = _resolve_speaker(node, char_map)

    buckets: dict[DirectiveChannel, list[AtomicDirective]] = {
        channel: [] for channel in CHANNEL_ORDER
    }

    _compile_timing(scene_state, node, buckets)
    _compile_camera(scene_state, node, buckets, speaker_id)
    _compile_character_channels(scene_state, node, buckets, speaker_id, char_map)
    _compile_tween(scene_state, node, buckets, speaker_id, char_map)
    _compile_sfx(scene_state, node, buckets)

    plan: list[dict[str, Any]] = []
    for channel in CHANNEL_ORDER:
        for directive in buckets[channel]:
            plan.append(directive.as_dict())
    return plan


# ──────────────────────────────────────────────────────────────────────────────
# Channel compilers
# ──────────────────────────────────────────────────────────────────────────────


def _compile_timing(
    scene_state: SceneState,
    node: PresentationNode,
    buckets: dict[DirectiveChannel, list[AtomicDirective]],
) -> None:
    base = (
        scene_state.timing.model_dump(exclude_none=True) if scene_state.timing else {}
    )
    override = _normalize_directive_payload(
        node.directives.timing, default_key="preset"
    )
    merged = _merge_payloads(base, override)
    if merged:
        buckets[DirectiveChannel.TIMING].append(
            AtomicDirective(
                channel=DirectiveChannel.TIMING,
                action="schedule",
                payload=merged,
            )
        )


def _compile_camera(
    scene_state: SceneState,
    node: PresentationNode,
    buckets: dict[DirectiveChannel, list[AtomicDirective]],
    speaker_id: str | None,
) -> None:
    base = (
        scene_state.camera.model_dump(exclude_none=True) if scene_state.camera else {}
    )
    override = _normalize_directive_payload(
        node.directives.camera, default_key="preset"
    )
    merged = _merge_payloads(base, override)
    if speaker_id and "focus" not in merged:
        merged["focus"] = speaker_id
    if merged:
        buckets[DirectiveChannel.CAMERA].append(
            AtomicDirective(
                channel=DirectiveChannel.CAMERA,
                action="frame",
                payload=merged,
            )
        )


def _compile_character_channels(
    scene_state: SceneState,
    node: PresentationNode,
    buckets: dict[DirectiveChannel, list[AtomicDirective]],
    speaker_id: str | None,
    char_map: dict[str, CharacterState],
) -> None:
    if not speaker_id:
        return
    char_state = char_map.get(speaker_id)

    portrait_payload = _derive_character_payload(
        char_state,
        node.directives.portrait,
        state_attr="portrait",
        default_key="asset",
    )
    if portrait_payload and not any(
        key in portrait_payload for key in ("asset", "preset", "path")
    ):
        portrait_payload = {}
    if portrait_payload:
        buckets[DirectiveChannel.PORTRAIT].append(
            AtomicDirective(
                channel=DirectiveChannel.PORTRAIT,
                action="set",
                target=speaker_id,
                payload=portrait_payload,
            )
        )

    expression_payload = _derive_character_payload(
        char_state,
        node.directives.expression,
        state_attr="default_expression",
        default_key="value",
        fallback={"value": "neutral"},
    )
    if expression_payload:
        buckets[DirectiveChannel.EXPRESSION].append(
            AtomicDirective(
                channel=DirectiveChannel.EXPRESSION,
                action="set",
                target=speaker_id,
                payload=expression_payload,
            )
        )

    pose_payload = _derive_character_payload(
        char_state,
        node.directives.pose,
        state_attr="default_pose",
        default_key="value",
        fallback={"value": "idle"},
    )
    if pose_payload:
        buckets[DirectiveChannel.POSE].append(
            AtomicDirective(
                channel=DirectiveChannel.POSE,
                action="set",
                target=speaker_id,
                payload=pose_payload,
            )
        )


def _compile_tween(
    scene_state: SceneState,
    node: PresentationNode,
    buckets: dict[DirectiveChannel, list[AtomicDirective]],
    speaker_id: str | None,
    char_map: dict[str, CharacterState],
) -> None:
    if speaker_id:
        char_state = char_map.get(speaker_id)
        if char_state and char_state.tween_preset:
            buckets[DirectiveChannel.TWEEN].append(
                AtomicDirective(
                    channel=DirectiveChannel.TWEEN,
                    action="apply_preset",
                    target=speaker_id,
                    payload={"preset": char_state.tween_preset},
                )
            )

    for index, raw in enumerate(node.directives.tween):
        payload = _normalize_directive_payload(raw, default_key="preset")
        if not payload:
            continue
        action = str(payload.pop("action", "step") or "step")
        target = payload.pop("target", speaker_id)
        payload.setdefault("index", index)
        buckets[DirectiveChannel.TWEEN].append(
            AtomicDirective(
                channel=DirectiveChannel.TWEEN,
                action=action,
                target=target,
                payload=payload,
            )
        )


def _compile_sfx(
    scene_state: SceneState,
    node: PresentationNode,
    buckets: dict[DirectiveChannel, list[AtomicDirective]],
) -> None:
    # Ambient bed is emitted first in alphabetical order for stability.
    for raw in sorted(scene_state.ambient_sfx, key=_ambient_sort_key):
        payload = _normalize_sfx_payload(raw, ambient=True)
        if not payload:
            continue
        action = payload.pop("action", "ambient")
        target = payload.pop("bus", None)
        buckets[DirectiveChannel.SFX].append(
            AtomicDirective(
                channel=DirectiveChannel.SFX,
                action=action,
                target=target,
                payload=payload,
            )
        )

    # Node-specific SFX retain their declared order.
    for raw in node.directives.sfx:
        payload = _normalize_sfx_payload(raw, ambient=False)
        if not payload:
            continue
        action = payload.pop("action", "play")
        target = payload.pop("bus", None)
        buckets[DirectiveChannel.SFX].append(
            AtomicDirective(
                channel=DirectiveChannel.SFX,
                action=action,
                target=target,
                payload=payload,
            )
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_speaker(
    node: PresentationNode, char_map: dict[str, CharacterState]
) -> str | None:
    if node.speaker and node.speaker in char_map:
        return node.speaker
    if node.speaker:
        lowered = node.speaker.lower()
        for char_id, state in char_map.items():
            if (state.display_name or "").lower() == lowered:
                return char_id
    if char_map:
        return next(iter(char_map))
    return None


def _derive_character_payload(
    char_state: CharacterState | None,
    override: str | dict[str, Any] | None,
    *,
    state_attr: str,
    default_key: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {}
    if char_state:
        source = getattr(char_state, state_attr, None)
        if isinstance(source, dict):
            base = _sorted_payload({k: v for k, v in source.items() if v is not None})
        elif source:
            base = {default_key: source}
        if char_state.slot and default_key == "asset":
            base.setdefault("slot", char_state.slot)
        if char_state.display_name:
            base.setdefault("label", char_state.display_name)
    if fallback and not base:
        base = dict(fallback)
    override_payload = _normalize_directive_payload(override, default_key=default_key)
    return _merge_payloads(base, override_payload)


def _normalize_directive_payload(
    value: str | dict[str, Any] | None,
    *,
    default_key: str,
) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        return {default_key: value}
    if isinstance(value, dict):
        return _sorted_payload({k: v for k, v in value.items() if v is not None})
    return {}


def _normalize_sfx_payload(
    value: str | dict[str, Any],
    *,
    ambient: bool,
) -> dict[str, Any]:
    if isinstance(value, str):
        return {"clip": value, "action": "ambient" if ambient else "play"}
    if isinstance(value, dict):
        payload = {k: v for k, v in value.items() if v is not None}
        if ambient:
            payload.setdefault("action", "ambient")
        return _sorted_payload(payload)
    return {}


def _merge_payloads(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    if not base and not override:
        return {}
    merged = dict(base)
    for key, value in override.items():
        merged[key] = value
    cleaned = {k: v for k, v in merged.items() if v not in (None, "", [], {})}
    return _sorted_payload(cleaned)


def _sorted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: payload[k] for k in sorted(payload)}


def _ambient_sort_key(item: str | dict[str, Any]) -> tuple[str, str]:
    if isinstance(item, dict):
        clip = str(item.get("clip") or item.get("id") or "")
        bus = str(item.get("bus") or "")
        return (clip.lower(), bus.lower())
    return (str(item).lower(), "")


__all__ = [
    "AtomicDirective",
    "DirectiveChannel",
    "SceneState",
    "CharacterState",
    "CameraState",
    "TimingState",
    "NodeDirectives",
    "PresentationNode",
    "compile_plan",
]
