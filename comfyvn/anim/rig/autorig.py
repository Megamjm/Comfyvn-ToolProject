from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

Vec3 = Tuple[float, float, float]

BREATH_ROLES = {"spine", "torso", "chest", "shoulder", "core"}
BLINK_ROLES = {"eyelid", "eye"}
MOUTH_ROLES = {"mouth", "jaw", "lip"}
ROOT_ID = "root"
DEFAULT_IDLE_DURATION = 2.4
DEFAULT_IDLE_FPS = 24

_DEFAULT_MOUTH_SHAPES = {
    "A": {"open": 0.85, "narrow": 0.25},
    "I": {"open": 0.35, "narrow": 0.7},
    "U": {"open": 0.55, "narrow": 0.4},
    "E": {"open": 0.65, "narrow": 0.35},
    "O": {"open": 0.75, "narrow": 0.25},
}


def _round(value: float, digits: int = 4) -> float:
    return float(f"{value:.{digits}f}")


def _round_vec(vec: Vec3, digits: int = 4) -> List[float]:
    return [_round(vec[0], digits), _round(vec[1], digits), _round(vec[2], digits)]


def _coerce_vec3(value: Any) -> Vec3:
    if isinstance(value, Mapping):
        x = float(value.get("x", 0.0) or 0.0)
        y = float(value.get("y", 0.0) or 0.0)
        z = float(value.get("z", value.get("depth", 0.0) or 0.0) or 0.0)
        return (x, y, z)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        lst = list(value[:3])
        while len(lst) < 3:
            lst.append(0.0)
        return (float(lst[0] or 0.0), float(lst[1] or 0.0), float(lst[2] or 0.0))
    try:
        scalar = float(value or 0.0)
    except Exception:
        scalar = 0.0
    return (scalar, 0.0, 0.0)


def _vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vec_length(vec: Vec3) -> float:
    return math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2)


def _vec_normalize(vec: Vec3) -> Vec3:
    length = _vec_length(vec)
    if length <= 1e-6:
        return (0.0, 1.0, 0.0)
    return (vec[0] / length, vec[1] / length, vec[2] / length)


def _slug(value: str, default: str = "character") -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value or "")
    text = text.strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or default


def _canonical_checksum(payload: Mapping[str, Any]) -> str:
    serial = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(serial).hexdigest()


def _extract_tags(value: Any) -> Tuple[str, ...]:
    tags: set[str] = set()
    if isinstance(value, (list, tuple, set)):
        for entry in value:
            text = str(entry or "").strip().lower()
            if text:
                tags.add(text)
    elif isinstance(value, str):
        for part in value.replace(",", " ").split():
            part = part.strip().lower()
            if part:
                tags.add(part)
    return tuple(sorted(tags))


def _resolve_role(anchor_id: str, tags: Iterable[str]) -> str:
    normalized_id = anchor_id.lower()
    tag_set = {tag.lower() for tag in tags}
    if ROOT_ID in {normalized_id, *tag_set}:
        return "root"
    if "head" in tag_set or "head" in normalized_id:
        return "head"
    if "neck" in tag_set or "neck" in normalized_id:
        return "neck"
    if {"mouth", "jaw", "lip"}.intersection(tag_set) or "mouth" in normalized_id:
        return "mouth"
    if "eye" in normalized_id or {"eye", "eyelid"}.intersection(tag_set):
        return "eyelid"
    if {"spine", "torso", "chest"}.intersection(tag_set) or any(
        key in normalized_id for key in ("spine", "chest", "torso")
    ):
        return "spine"
    if any(key in normalized_id for key in ("arm", "hand", "shoulder")) or {
        "arm",
        "hand",
        "shoulder",
    }.intersection(tag_set):
        return "arm"
    if any(key in normalized_id for key in ("leg", "thigh", "foot")) or {
        "leg",
        "foot",
        "thigh",
    }.intersection(tag_set):
        return "leg"
    if "brow" in normalized_id or "brow" in tag_set:
        return "brow"
    return "aux"


def _normalize_anchor(raw: Mapping[str, Any], index: int) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Anchor payload must be a mapping.")
    anchor_id = str(
        raw.get("id")
        or raw.get("name")
        or raw.get("anchor")
        or raw.get("key")
        or f"anchor_{index:02d}"
    ).strip()
    if not anchor_id:
        raise ValueError("Anchor entries must include an 'id'.")
    parent = raw.get("parent") or raw.get("parent_id") or raw.get("parentId")
    parent_id = str(parent).strip() if parent else None
    position = _coerce_vec3(raw.get("position") or raw.get("pos") or raw.get("xyz"))
    tags = _extract_tags(raw.get("tags"))
    weight_raw = raw.get("weight") or raw.get("influence") or 1.0
    try:
        weight = float(weight_raw)
    except Exception:
        weight = 1.0

    meta: Dict[str, Any] = {}
    for key, value in raw.items():
        if key in {
            "id",
            "name",
            "anchor",
            "key",
            "parent",
            "parent_id",
            "parentId",
            "position",
            "pos",
            "xyz",
            "tags",
            "weight",
            "influence",
        }:
            continue
        meta[key] = value

    role = _resolve_role(anchor_id, tags)
    return {
        "id": anchor_id,
        "parent": parent_id,
        "position": position,
        "tags": tags,
        "weight": weight,
        "meta": meta,
        "role": role,
    }


def _derive_constraints(role: str, length: float) -> Dict[str, Any]:
    length = max(length, 1e-4)
    base_angle = 35.0
    if role == "head":
        base_angle = 55.0
    elif role == "neck":
        base_angle = 45.0
    elif role == "spine":
        base_angle = 25.0
    elif role == "arm":
        base_angle = 75.0
    elif role == "leg":
        base_angle = 50.0
    elif role in {"mouth", "brow"}:
        base_angle = 15.0
    elif role in {"eyelid"}:
        base_angle = 10.0
    translate_limit = min(0.08, max(0.02, length * 0.35))
    if role in {"mouth", "jaw"}:
        translate_limit = min(0.06, max(0.015, length * 0.5))
    if role in {"eyelid"}:
        translate_limit = min(0.02, translate_limit * 0.5)
    scale_min = 0.9
    scale_max = 1.12
    if role in {"mouth", "eyelid"}:
        scale_min = 0.7
        scale_max = 1.2
    return {
        "rotation_deg": {"min": _round(-base_angle), "max": _round(base_angle)},
        "twist_deg": {
            "min": _round(-base_angle * 0.35),
            "max": _round(base_angle * 0.35),
        },
        "translate": {
            axis: (-_round(translate_limit), _round(translate_limit))
            for axis in ("x", "y", "z")
        },
        "scale": {"min": _round(scale_min), "max": _round(scale_max)},
    }


def _ensure_root_anchor(anchors: MutableMapping[str, Dict[str, Any]]) -> None:
    if ROOT_ID in anchors:
        entry = anchors[ROOT_ID]
        entry["parent"] = None
        entry["role"] = "root"
        entry["position"] = entry.get("position") or (0.0, 0.0, 0.0)
        entry["tags"] = tuple({*entry.get("tags", ()), ROOT_ID})
        return
    anchors[ROOT_ID] = {
        "id": ROOT_ID,
        "parent": None,
        "position": (0.0, 0.0, 0.0),
        "tags": (ROOT_ID,),
        "weight": 1.0,
        "meta": {},
        "role": "root",
    }


def _topological_order(anchors: Mapping[str, Dict[str, Any]]) -> List[str]:
    children: Dict[str, List[str]] = {}
    for anchor_id, anchor in anchors.items():
        parent = anchor.get("parent") or ROOT_ID
        if parent not in anchors:
            parent = ROOT_ID
        children.setdefault(parent, []).append(anchor_id)
    for child_list in children.values():
        child_list.sort()
    order: List[str] = []
    queue: List[str] = [ROOT_ID]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        order.append(current)
        queue.extend(children.get(current, []))
    # include any isolated anchors deterministically
    for anchor_id in sorted(anchors):
        if anchor_id not in seen:
            order.append(anchor_id)
    return order


def build_rig(
    anchors: Sequence[Mapping[str, Any]],
    *,
    character: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Convert an anchor payload into a deterministic bone hierarchy and constraints.
    """

    normalized: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(anchors or ()):
        anchor = _normalize_anchor(raw, index)
        anchor_id = anchor["id"]
        if anchor_id in normalized:
            raise ValueError(f"Duplicate anchor id detected: {anchor_id}")
        normalized[anchor_id] = anchor

    _ensure_root_anchor(normalized)

    options = dict(options or {}) if isinstance(options, Mapping) else {}
    root_override = options.get("root")
    if isinstance(root_override, Mapping):
        override_anchor = _normalize_anchor(root_override, len(normalized))
        override_anchor["parent"] = None
        override_anchor["role"] = "root"
        normalized[ROOT_ID] = override_anchor

    order = _topological_order(normalized)
    root_position = normalized[ROOT_ID]["position"]

    bones: List[Dict[str, Any]] = []
    constraints: Dict[str, Dict[str, Any]] = {}
    rest_pose: Dict[str, Dict[str, Any]] = {}

    for anchor_id in order:
        if anchor_id == ROOT_ID:
            constraints[anchor_id] = _derive_constraints("root", 0.0)
            rest_pose[anchor_id] = {
                "position": _round_vec(root_position),
                "translate": [0.0, 0.0, 0.0],
                "rotate": 0.0,
                "scale": [1.0, 1.0, 1.0],
            }
            continue
        anchor = normalized[anchor_id]
        parent_id = anchor.get("parent") or ROOT_ID
        if parent_id not in normalized:
            parent_id = ROOT_ID
        parent = normalized[parent_id]
        offset = _vec_sub(anchor["position"], parent["position"])
        length = _vec_length(offset)
        orientation = _vec_normalize(offset)
        bones.append(
            {
                "id": anchor_id,
                "parent": parent_id,
                "length": _round(length, 5),
                "rest_offset": _round_vec(offset, 5),
                "orientation": _round_vec(orientation, 5),
                "tags": list(anchor.get("tags") or ()),
                "role": anchor.get("role", "aux"),
                "weight": anchor.get("weight", 1.0),
            }
        )
        constraints[anchor_id] = _derive_constraints(anchor.get("role", "aux"), length)
        rest_pose[anchor_id] = {
            "position": _round_vec(anchor["position"], 5),
            "translate": [0.0, 0.0, 0.0],
            "rotate": 0.0,
            "scale": [1.0, 1.0, 1.0],
        }

    rig_payload = {
        "character": character or options.get("character") or "anonymous",
        "root": {
            "id": ROOT_ID,
            "position": _round_vec(root_position),
        },
        "bones": bones,
        "constraints": constraints,
        "rest_pose": rest_pose,
    }
    rig_payload["checksum"] = _canonical_checksum(rig_payload)

    mouth_shapes = _build_mouth_shapes(rig_payload)
    stats = _compute_stats(rig_payload, mouth_shapes)

    rig_payload["mouth_shapes"] = mouth_shapes
    rig_payload["stats"] = stats
    return rig_payload


def _build_mouth_shapes(rig_payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    bones: Sequence[Mapping[str, Any]] = rig_payload.get("bones", [])
    constraints: Mapping[str, Mapping[str, Any]] = rig_payload.get("constraints", {})
    mouth_bones = [
        bone
        for bone in bones
        if bone.get("role") in MOUTH_ROLES
        or "mouth" in (bone.get("id") or "").lower()
        or "jaw" in (bone.get("id") or "").lower()
    ]
    if not mouth_bones:
        return {key: {} for key in _DEFAULT_MOUTH_SHAPES}

    shapes: Dict[str, Dict[str, Any]] = {}
    for shape, weights in _DEFAULT_MOUTH_SHAPES.items():
        per_bone: Dict[str, Any] = {}
        for index, bone in enumerate(mouth_bones):
            bone_id = str(bone.get("id"))
            limit = constraints.get(bone_id, {})
            translate_limits = limit.get("translate", {})
            y_limit = float(translate_limits.get("y", (0.0, 0.04))[1])
            open_amt = _round(min(y_limit * 0.9, 0.06) * weights["open"], 5)
            narrow = weights["narrow"]
            scale_x = _round(1.0 - min(0.25, 0.12 * narrow), 4)
            scale_y = _round(1.0 + min(0.3, 0.2 * weights["open"]), 4)
            easing = 1.0 + index * 0.05
            per_bone[bone_id] = {
                "translate": [0.0, _round(open_amt * easing, 5), 0.0],
                "rotate": 0.0,
                "scale": [scale_x, scale_y, 1.0],
            }
        shapes[shape] = per_bone
    return shapes


def _compute_stats(
    rig_payload: Mapping[str, Any], mouth_shapes: Mapping[str, Any]
) -> Dict[str, Any]:
    bones: Sequence[Mapping[str, Any]] = rig_payload.get("bones", [])
    role_counts: Dict[str, int] = {}
    for bone in bones:
        role = str(bone.get("role") or "aux")
        role_counts[role] = role_counts.get(role, 0) + 1
    mouth_keys = [key for key, payload in mouth_shapes.items() if payload]
    return {
        "bone_count": len(bones),
        "role_counts": role_counts,
        "mouth_shapes": mouth_keys,
    }


def generate_idle_cycle(
    rig_payload: Mapping[str, Any],
    *,
    duration: float = DEFAULT_IDLE_DURATION,
    fps: int = DEFAULT_IDLE_FPS,
) -> Dict[str, Any]:
    bones: Sequence[Mapping[str, Any]] = rig_payload.get("bones", [])
    constraints: Mapping[str, Mapping[str, Any]] = rig_payload.get("constraints", {})
    checksum = rig_payload.get("checksum", "")
    fps = max(1, int(fps))
    duration = max(0.5, float(duration))
    total_frames = max(1, int(duration * fps))
    rng = random.Random(int(checksum[:8] or "0", 16))

    breath_amplitude: Dict[str, float] = {}
    blink_targets: List[str] = []
    mouth_targets: List[str] = []

    for bone in bones:
        bone_id = str(bone.get("id"))
        role = str(bone.get("role") or "aux")
        limit = constraints.get(bone_id, {})
        translate_limits = limit.get("translate", {})
        y_limit = float(translate_limits.get("y", (0.0, 0.02))[1])
        if role in BREATH_ROLES:
            amplitude = min(0.05, max(0.01, y_limit * 0.6))
            breath_amplitude[bone_id] = amplitude
        if role in BLINK_ROLES:
            blink_targets.append(bone_id)
        if role in MOUTH_ROLES:
            mouth_targets.append(bone_id)

    blink_frames: set[int] = set()
    if blink_targets:
        base_spacing = max(6, total_frames // 3)
        start_frame = max(2, total_frames // 6)
        frame = start_frame
        while frame < total_frames:
            window = rng.randint(2, 4)
            for offset in range(window):
                blink_frames.add(frame + offset)
            frame += base_spacing + rng.randint(-2, 2)

    frames: List[Dict[str, Any]] = []
    for frame_index in range(total_frames):
        t = frame_index / fps
        phase = (frame_index % total_frames) / total_frames
        breath_value = math.sin(phase * 2.0 * math.pi)
        frame_bones: Dict[str, Any] = {}
        for bone in bones:
            bone_id = str(bone.get("id"))
            transform = {
                "translate": [0.0, 0.0, 0.0],
                "rotate": 0.0,
                "scale": [1.0, 1.0, 1.0],
            }
            if bone_id in breath_amplitude:
                amplitude = breath_amplitude[bone_id]
                transform["translate"][1] = _round(amplitude * breath_value, 5)
            if bone_id in mouth_targets:
                phase_seed = int(
                    hashlib.sha1(f"{checksum}:{bone_id}".encode("utf-8")).hexdigest()[
                        :8
                    ],
                    16,
                )
                phase_offset = (phase_seed % 360) / 180.0
                oscillation = math.sin((phase * 4.0 + phase_offset) * math.pi)
                mouth_limit = min(
                    0.02,
                    constraints.get(bone_id, {})
                    .get("translate", {})
                    .get("y", (0.0, 0.02))[1],
                )
                transform["translate"][1] = _round(
                    transform["translate"][1] + oscillation * mouth_limit * 0.3, 5
                )
            if bone_id in blink_targets:
                if frame_index in blink_frames:
                    blink_phase = (frame_index % 3) / 3.0
                    closedness = math.sin(blink_phase * math.pi)
                    transform["scale"][1] = _round(
                        max(0.15, 1.0 - 0.85 * closedness), 4
                    )
                else:
                    transform["scale"][1] = 1.0
            frame_bones[bone_id] = transform
        frames.append({"time": _round(t, 5), "bones": frame_bones})
    return {"fps": fps, "duration": duration, "frames": frames}


__all__ = ["build_rig", "generate_idle_cycle"]
