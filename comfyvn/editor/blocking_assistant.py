from __future__ import annotations

import hashlib
import json
import logging
import random
import textwrap
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from comfyvn.core import modder_hooks
from comfyvn.core.modder_hooks import HookSpec
from comfyvn.llm.orchestrator import ROLE_ORCHESTRATOR

LOGGER = logging.getLogger(__name__)

_SCHEMA_VERSION = "p6.blocking.v1"

_STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "into",
    "over",
    "then",
    "this",
    "have",
    "when",
    "just",
    "your",
    "will",
    "about",
    "they",
    "their",
    "them",
    "because",
    "while",
    "where",
    "there",
    "after",
    "before",
    "through",
    "around",
    "across",
    "under",
    "above",
    "between",
}

ANGLE_LIBRARY: list[dict[str, Any]] = [
    {
        "key": "wide_establishing",
        "label": "Wide Establishing",
        "composition": "Set geography; include key characters and props.",
        "camera": {
            "lens_mm": 24,
            "height": "eye",
            "movement": "locked tripod",
            "notes": "Establishes room layout and relative positions.",
        },
    },
    {
        "key": "medium_two_shot",
        "label": "Medium Two-Shot",
        "composition": "Waist-up on lead and support, angled for conversation.",
        "camera": {
            "lens_mm": 35,
            "height": "eye",
            "movement": "slow dolly-in",
            "notes": "Keeps energy while staying intimate.",
        },
    },
    {
        "key": "over_shoulder",
        "label": "Over-the-Shoulder",
        "composition": "Anchor foreground shoulder; track eyeline to subject.",
        "camera": {
            "lens_mm": 50,
            "height": "shoulder",
            "movement": "gentle rack-focus",
            "notes": "Emphasises point-of-view tension.",
        },
    },
    {
        "key": "motivated_closeup",
        "label": "Motivated Close-Up",
        "composition": "Tight headroom, background falls off.",
        "camera": {
            "lens_mm": 85,
            "height": "eye",
            "movement": "locked with micro push",
            "notes": "Use on emotional peak or reveal.",
        },
    },
    {
        "key": "profile_tracking",
        "label": "Profile Tracking",
        "composition": "Profile medium shot; follow lateral motion.",
        "camera": {
            "lens_mm": 40,
            "height": "eye",
            "movement": "track left-to-right",
            "notes": "Great for walk-and-talk energy.",
        },
    },
    {
        "key": "cutaway_detail",
        "label": "Cutaway Detail",
        "composition": "Isolate prop or silent reaction.",
        "camera": {
            "lens_mm": 60,
            "height": "prop-level",
            "movement": "static macro",
            "notes": "Breaks rhythm; supports beat emphasis.",
        },
    },
    {
        "key": "environment_plate",
        "label": "Environment Plate",
        "composition": "Hold on empty space or motif.",
        "camera": {
            "lens_mm": 28,
            "height": "waist",
            "movement": "locked or drift",
            "notes": "Breather to underscore tone.",
        },
    },
    {
        "key": "pov_insert",
        "label": "POV Insert",
        "composition": "Direct POV framing; lean into character perception.",
        "camera": {
            "lens_mm": 35,
            "height": "eye",
            "movement": "handheld sway",
            "notes": "Use sparingly for subjective rush.",
        },
    },
]


def _ensure_hook() -> None:
    if "on_blocking_suggested" in modder_hooks.HOOK_SPECS:
        return
    spec = HookSpec(
        name="on_blocking_suggested",
        description="Emitted when the blocking assistant generates a deterministic shot plan.",
        payload_fields={
            "scene_id": "Scene identifier supplied in the request payload.",
            "node_id": "Node identifier resolved during plan generation.",
            "plan_digest": "SHA-1 digest of the computed BlockingPlan payload.",
            "seed": "Deterministic integer seed used to sample angles and beats.",
            "shots": "Ordered list of shot identifiers included in the plan.",
            "beats": "Ordered list of beat identifiers included in the plan.",
            "pov": "POV identifier supplied or inferred for the plan.",
            "style": "Optional style string forwarded from the request.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="editor.blocking.suggested",
        rest_event="on_blocking_suggested",
    )
    modder_hooks.HOOK_SPECS[spec.name] = spec
    bus = getattr(modder_hooks, "_BUS", None)
    if bus and getattr(bus, "_listeners", None) is not None:
        with bus._lock:  # type: ignore[attr-defined]
            bus._listeners.setdefault(spec.name, [])  # type: ignore[attr-defined]


def _safe_text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _scene_identifier(scene: Mapping[str, Any]) -> str:
    for key in ("id", "scene_id", "slug", "name"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "scene"


def _find_node(
    scene: Mapping[str, Any], requested_id: Optional[str]
) -> Optional[Mapping[str, Any]]:
    nodes = scene.get("nodes")
    if isinstance(nodes, list):
        if requested_id:
            for node in nodes:
                if isinstance(node, Mapping):
                    node_id = _safe_text(node.get("id"))
                    if node_id and node_id == requested_id:
                        return node
        for node in nodes:
            if isinstance(node, Mapping):
                return node
    return None


def _iter_lines(node: Optional[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    if not isinstance(node, Mapping):
        return
    for key in ("lines", "dialogue", "script"):
        payload = node.get(key)
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, Mapping):
                    yield entry


def _collect_characters(
    scene: Mapping[str, Any], node: Optional[Mapping[str, Any]]
) -> list[str]:
    roster: list[str] = []
    cast = scene.get("cast")
    if isinstance(cast, list):
        for member in cast:
            if isinstance(member, Mapping):
                name = _safe_text(member.get("name") or member.get("id"))
                if name and name not in roster:
                    roster.append(name)
            elif (
                isinstance(member, str)
                and member.strip()
                and member.strip() not in roster
            ):
                roster.append(member.strip())

    if isinstance(node, Mapping):
        speaker = _safe_text(node.get("speaker") or node.get("pov"))
        if speaker and speaker not in roster:
            roster.insert(0, speaker)
        meta = node.get("metadata")
        if isinstance(meta, Mapping):
            main = _safe_text(meta.get("speaker_name") or meta.get("pov_name"))
            if main and main not in roster:
                roster.append(main)
            cast_meta = meta.get("cast")
            if isinstance(cast_meta, list):
                for entry in cast_meta:
                    if isinstance(entry, Mapping):
                        label = _safe_text(entry.get("name") or entry.get("id"))
                        if label and label not in roster:
                            roster.append(label)

    return roster


def _infer_emotion(text: str) -> str:
    lowered = text.lower()
    if "?" in lowered and "!" in lowered:
        return "surprised"
    if lowered.endswith("!") or "!" in lowered:
        return "excited"
    if lowered.endswith("?"):
        return "curious"
    if "..." in lowered:
        return "pensive"
    if any(word in lowered for word in ("whisper", "quiet", "softly")):
        return "quiet"
    return "neutral"


def _keywords(text: str) -> list[str]:
    words = []
    for raw in text.split():
        token = "".join(ch for ch in raw.lower() if ch.isalnum())
        if len(token) < 4 or token in _STOPWORDS:
            continue
        if token not in words:
            words.append(token)
        if len(words) >= 5:
            break
    return words


class BlockingBeat(BaseModel):
    id: str
    order: int
    summary: str
    focus: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    emotion: str | None = None
    keywords: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class BlockingShot(BaseModel):
    id: str
    angle_key: str
    label: str
    composition: str
    focus: list[str] = Field(default_factory=list)
    beat_ids: list[str] = Field(default_factory=list)
    camera: dict[str, Any] = Field(default_factory=dict)
    notes: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class BlockingPlan(BaseModel):
    schema: str
    summary: str
    context: dict[str, Any]
    shots: list[BlockingShot]
    beats: list[BlockingBeat]
    determinism: dict[str, Any]
    narrator_plan: dict[str, Any] | None = None
    request: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class BlockingRequest(BaseModel):
    scene: dict[str, Any] = Field(default_factory=dict)
    node: dict[str, Any] | None = None
    node_id: str | None = None
    pov: str | None = None
    prompt: str | None = None
    angles: int = Field(default=3, ge=1, le=8)
    beats: int = Field(default=2, ge=1, le=10)
    style: str | None = None
    seed: int | None = None
    dry_run: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


def _seed_for_request(
    request: BlockingRequest,
    *,
    scene_id: str,
    node_id: Optional[str],
    beat_material: Sequence[str],
) -> int:
    material = {
        "scene": scene_id,
        "node": node_id or "",
        "angles": request.angles,
        "beats": request.beats,
        "pov": request.pov or "",
        "style": request.style or "",
        "prompt": request.prompt or "",
        "beat_material": list(beat_material),
    }
    digest = hashlib.sha1(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    seed = int(digest[:8], 16)
    if request.seed is not None:
        seed ^= int(request.seed) & 0xFFFFFFFF
    return seed


def _assign_beats(beats: Sequence[BlockingBeat], shot_count: int) -> dict[str, int]:
    mapping: dict[str, int] = {}
    if not beats or shot_count <= 0:
        return mapping
    for idx, beat in enumerate(beats):
        mapping[beat.id] = idx % shot_count
    return mapping


class BlockingAssistant:
    """Generate deterministic blocking suggestions for a scene context."""

    def __init__(self) -> None:
        _ensure_hook()

    def suggest(
        self,
        request: BlockingRequest,
        *,
        use_role_mapping: bool = False,
    ) -> BlockingPlan:
        scene = dict(request.scene or {})
        scene_id = _scene_identifier(scene)
        node = request.node if request.node else _find_node(scene, request.node_id)
        node_id = _safe_text(
            node.get("id") if isinstance(node, Mapping) else request.node_id or ""
        )
        characters = _collect_characters(scene, node)
        if not characters:
            characters = ["Narrator"]

        lines = list(_iter_lines(node))
        beat_material = [
            _safe_text(entry.get("text") or entry.get("summary"))
            for entry in lines[: request.beats * 2]
        ]
        seed = _seed_for_request(
            request,
            scene_id=scene_id,
            node_id=node_id or None,
            beat_material=beat_material,
        )
        beats = self._build_beats(
            request=request,
            scene_id=scene_id,
            node_id=node_id or None,
            characters=characters,
            lines=lines,
        )
        shots = self._build_shots(
            request=request,
            characters=characters,
            beats=beats,
            seed=seed,
        )

        context = {
            "scene_id": scene_id,
            "scene_title": _safe_text(scene.get("title"), default=scene_id.title()),
            "node_id": node_id or None,
            "pov": request.pov
            or _safe_text(scene.get("pov"))
            or _safe_text(scene.get("default_pov")),
            "characters": characters,
        }

        summary = (
            f"{context['scene_title']} → {len(shots)} shot plan covering "
            f"{len(beats)} beats (seed {seed:08x})."
        )

        narrator_plan: dict[str, Any] | None = None
        if use_role_mapping:
            message = request.prompt or summary
            context_entries = [
                {
                    "speaker": beat.focus[0] if beat.focus else "Narrator",
                    "text": beat.summary,
                }
                for beat in beats
            ]
            try:
                narrator_plan = ROLE_ORCHESTRATOR.plan(
                    role="Narrator",
                    message=message,
                    context=context_entries,
                    dry_run=True,
                )
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Narrator plan lookup failed", exc_info=True)
                narrator_plan = None

        plan_payload = {
            "schema": _SCHEMA_VERSION,
            "summary": summary,
            "context": context,
            "shots": [shot.model_dump(mode="python") for shot in shots],
            "beats": [beat.model_dump(mode="python") for beat in beats],
            "determinism": {
                "seed": seed,
                "seed_hex": f"{seed:08x}",
                "digest": None,
            },
            "narrator_plan": narrator_plan,
            "request": request.model_dump(mode="python"),
        }

        digest = hashlib.sha1(
            json.dumps(
                {
                    "shots": plan_payload["shots"],
                    "beats": plan_payload["beats"],
                    "context": context,
                    "seed": seed,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        plan_payload["determinism"]["digest"] = digest

        plan = BlockingPlan.model_validate(plan_payload)

        try:
            modder_hooks.emit(
                "on_blocking_suggested",
                {
                    "scene_id": context["scene_id"],
                    "node_id": context["node_id"],
                    "plan_digest": digest,
                    "seed": seed,
                    "shots": [shot.id for shot in plan.shots],
                    "beats": [beat.id for beat in plan.beats],
                    "pov": context["pov"],
                    "style": request.style,
                    "timestamp": time.time(),
                },
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Blocking hook emission failed", exc_info=True)

        return plan

    def _build_beats(
        self,
        *,
        request: BlockingRequest,
        scene_id: str,
        node_id: Optional[str],
        characters: Sequence[str],
        lines: Sequence[Mapping[str, Any]],
    ) -> list[BlockingBeat]:
        beats: list[BlockingBeat] = []
        limit = max(1, request.beats)
        for idx, entry in enumerate(lines):
            if len(beats) >= limit:
                break
            text = _safe_text(
                entry.get("text")
                or entry.get("summary")
                or entry.get("description")
                or entry.get("action")
            )
            if not text and not entry:
                continue
            summary = textwrap.shorten(text, width=96, placeholder="…") or (
                f"Beat {idx + 1}"
            )
            speaker = _safe_text(
                entry.get("speaker")
                or entry.get("character")
                or entry.get("name")
                or entry.get("pov")
            )
            focus = []
            if speaker:
                focus.append(speaker)
            for name in (
                entry.get("focus", []) if isinstance(entry.get("focus"), list) else []
            ):
                if isinstance(name, str) and name and name not in focus:
                    focus.append(name)
            for char in characters:
                if char not in focus:
                    focus.append(char)
                if len(focus) >= 3:
                    break
            beat = BlockingBeat(
                id=f"beat-{idx + 1:02d}",
                order=idx + 1,
                summary=summary,
                focus=focus,
                source={
                    "scene_id": scene_id,
                    "node_id": node_id,
                    "index": idx,
                    "type": entry.get("type") or "line",
                },
                emotion=_infer_emotion(text),
                keywords=_keywords(text),
            )
            beats.append(beat)

        while len(beats) < limit:
            order = len(beats) + 1
            template_focus = list(characters[:2]) or ["Narrator"]
            beat = BlockingBeat(
                id=f"beat-{order:02d}",
                order=order,
                summary=f"Open beat for {template_focus[0]}",
                focus=template_focus,
                source={"scene_id": scene_id, "node_id": node_id, "type": "synthetic"},
                emotion="neutral",
                keywords=[],
            )
            beats.append(beat)

        return beats

    def _build_shots(
        self,
        *,
        request: BlockingRequest,
        characters: Sequence[str],
        beats: Sequence[BlockingBeat],
        seed: int,
    ) -> list[BlockingShot]:
        library = list(ANGLE_LIBRARY)
        rng = random.Random(seed)
        rng.shuffle(library)

        shot_count = max(1, request.angles)
        assignment = _assign_beats(beats, shot_count)
        shots: list[BlockingShot] = []
        for idx in range(shot_count):
            template = library[idx % len(library)]
            beat_ids = [beat.id for beat in beats if assignment.get(beat.id, 0) == idx]
            if not beat_ids and beats:
                beat_ids = [beats[min(idx, len(beats) - 1)].id]
            focus: list[str] = []
            for beat in beats:
                if beat.id in beat_ids:
                    for name in beat.focus:
                        if name not in focus:
                            focus.append(name)
            if not focus:
                focus = list(characters[:2]) or ["Narrator"]

            composition = f"{template['composition']} Focus on {', '.join(focus[:3])}."
            notes = {}
            if request.style:
                notes["style"] = request.style

            shot = BlockingShot(
                id=f"shot-{idx + 1:02d}",
                angle_key=template["key"],
                label=template["label"],
                composition=composition,
                focus=focus,
                beat_ids=beat_ids,
                camera={
                    "lens_mm": template["camera"]["lens_mm"],
                    "height": template["camera"]["height"],
                    "movement": template["camera"]["movement"],
                    "notes": template["camera"]["notes"],
                },
                notes=notes,
            )
            shots.append(shot)

        return shots


__all__ = [
    "BlockingAssistant",
    "BlockingPlan",
    "BlockingRequest",
    "BlockingShot",
    "BlockingBeat",
]
