from __future__ import annotations

import ast
import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

POSE_ANCHORS: Dict[str, Dict[str, float]] = {
    "face_forehead": {"x": 0.5, "y": 0.16},
    "hairline": {"x": 0.5, "y": 0.12},
    "eyes": {"x": 0.5, "y": 0.24},
    "cheek_l": {"x": 0.35, "y": 0.3},
    "cheek_r": {"x": 0.65, "y": 0.3},
    "mouth": {"x": 0.5, "y": 0.36},
    "upper_torso": {"x": 0.5, "y": 0.48},
    "left_hand": {"x": 0.28, "y": 0.68},
    "right_hand": {"x": 0.72, "y": 0.68},
    "feet": {"x": 0.5, "y": 0.9},
}

LEGACY_ANCHORS: Dict[str, Dict[str, float]] = {
    "root": {"x": 0.5, "y": 0.5},
    "left": {"x": 0.18, "y": 0.6},
    "right": {"x": 0.82, "y": 0.6},
    "center": {"x": 0.5, "y": 0.55},
    "upper": {"x": 0.5, "y": 0.25},
    "lower": {"x": 0.5, "y": 0.85},
    "foreground": {"x": 0.5, "y": 0.9},
    "background": {"x": 0.5, "y": 0.2},
}

ANCHORS: Dict[str, Dict[str, Any]] = {
    **{
        key: {"x": value["x"], "y": value["y"], "group": "pose"}
        for key, value in POSE_ANCHORS.items()
    },
    **{
        key: {"x": value["x"], "y": value["y"], "group": "legacy"}
        for key, value in LEGACY_ANCHORS.items()
    },
}

Z_ORDER_VALUES: Tuple[str, ...] = (
    "under_bg",
    "under_portrait",
    "over_portrait",
    "over_ui",
)

TWEEN_KINDS: Tuple[str, ...] = ("fade", "drift", "pulse", "rotate", "scale")
MIN_TWEEN_DURATION = 0.05
MAX_TWEEN_DURATION = 6.0

DEFAULT_TWEEN: Dict[str, Any] = {
    "kind": "fade",
    "duration": 0.45,
    "ease": "easeInOutCubic",
    "hold": 0.0,
    "stop_at_end": True,
    "loop": False,
    "caps": {
        "duration": {"min": MIN_TWEEN_DURATION, "max": MAX_TWEEN_DURATION},
        "kinds": list(TWEEN_KINDS),
    },
}

ALPHA_MODES: Tuple[str, ...] = ("premultiplied", "sdf_outline")
DEFAULT_GENERATOR = "visual_style_mapper"
CONDITION_WHITELIST: Tuple[str, ...] = ("weather", "pose", "emotion")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_prop_id(value: Any) -> str:
    if not isinstance(value, str):
        value = str(value)
    prop_id = value.strip()
    if not prop_id:
        raise ValueError("prop_id must be a non-empty string")
    return prop_id


def _serialise_metadata(data: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    serialisable: Dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        try:
            json.dumps(value)
        except TypeError:
            continue
        serialisable[key] = value
    return serialisable


def _digest_payload(
    prop_id: str,
    asset: str,
    style: Optional[str],
    tags: Iterable[str],
    checksum: Optional[str],
    metadata: Mapping[str, Any],
    generator: str,
    alpha_mode: str,
) -> str:
    payload = {
        "prop_id": prop_id,
        "asset": asset,
        "style": style,
        "tags": sorted(set(tags)),
        "checksum": checksum or "",
        "metadata": metadata,
        "generator": generator,
        "alpha_mode": alpha_mode,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()


def _build_thumbnail(digest: str) -> str:
    return f"thumbnails/props/{digest[:12]}.png"


def _coerce_tags(values: Optional[Iterable[str]]) -> Tuple[str, ...]:
    tags: list[str] = []
    if values:
        for entry in values:
            if not isinstance(entry, str):
                continue
            cleaned = entry.strip()
            if cleaned:
                tags.append(cleaned)
    return tuple(dict.fromkeys(tags))


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return float(int(value))
    try:
        return float(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"expected numeric value, received {value!r}") from exc


def _coerce_alpha_mode(value: Optional[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        return ALPHA_MODES[0]
    candidate = value.strip().lower()
    if candidate not in ALPHA_MODES:
        raise ValueError(f"alpha_mode must be one of {', '.join(ALPHA_MODES)}")
    return candidate


def _coerce_generator(value: Optional[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_GENERATOR
    return value.strip()


@dataclass(slots=True)
class _EnsuredProp:
    prop_id: str
    checksum: str
    asset: str
    style: Optional[str]
    tags: Tuple[str, ...]
    thumbnail: str
    sidecar: Dict[str, Any]
    provenance: Dict[str, Any]
    generator: str
    alpha_mode: str


class _ConditionEvaluator(ast.NodeVisitor):
    """Deterministic, safe evaluator for simple boolean expressions."""

    def __init__(self, context: Mapping[str, Any], allowed_names: Iterable[str]):
        self._context = context
        self._allowed: Tuple[str, ...] = tuple(dict.fromkeys(allowed_names))

    # pylint: disable=missing-docstring, invalid-name
    def visit_Expression(self, node: ast.Expression) -> bool:  # type: ignore[override]
        return bool(self.visit(node.body))

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:  # type: ignore[override]
        values = [bool(self.visit(value)) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise ValueError("unsupported boolean operator")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> bool:  # type: ignore[override]
        if isinstance(node.op, ast.Not):
            return not bool(self.visit(node.operand))
        raise ValueError("unsupported unary operator")

    def visit_Compare(self, node: ast.Compare) -> bool:  # type: ignore[override]
        if len(node.ops) != len(node.comparators):
            raise ValueError("malformed comparison expression")
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            left_val = self._coerce(left)
            right_val = self._coerce(right)
            if isinstance(op, ast.Gt):
                ok = left_val > right_val
            elif isinstance(op, ast.GtE):
                ok = left_val >= right_val
            elif isinstance(op, ast.Lt):
                ok = left_val < right_val
            elif isinstance(op, ast.LtE):
                ok = left_val <= right_val
            elif isinstance(op, ast.Eq):
                ok = left_val == right_val
            elif isinstance(op, ast.NotEq):
                ok = left_val != right_val
            else:
                raise ValueError("unsupported comparison operator")
            if not ok:
                return False
            left = right
        return True

    def visit_Name(self, node: ast.Name) -> Any:  # type: ignore[override]
        if node.id not in self._allowed:
            raise ValueError(f"unsupported condition variable '{node.id}'")
        return self._context.get(node.id, None)

    def visit_Constant(self, node: ast.Constant) -> Any:  # type: ignore[override]
        return node.value

    def generic_visit(self, node: ast.AST) -> Any:  # type: ignore[override]
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    @staticmethod
    def _coerce(value: Any) -> Any:
        if isinstance(value, (int, float, bool)):
            return float(value)
        return value


def _evaluate_condition(
    expression: str, context: Mapping[str, Any], allowed_names: Iterable[str]
) -> bool:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid condition '{expression}'") from exc
    evaluator = _ConditionEvaluator(context, allowed_names)
    return bool(evaluator.visit(tree))


def _build_context(
    state: Optional[Mapping[str, Any]], allowed_names: Iterable[str]
) -> Dict[str, Any]:
    context: Dict[str, Any] = {name: None for name in allowed_names}
    if not isinstance(state, Mapping):
        return context

    def _maybe_assign(key: str, value: Any) -> None:
        if key in context:
            context[key] = value

    for key, value in state.items():
        if not isinstance(key, str):
            continue
        if key == "vars" and isinstance(value, Mapping):
            for inner_key, inner_value in value.items():
                if not isinstance(inner_key, str):
                    continue
                _maybe_assign(inner_key, inner_value)
            continue
        _maybe_assign(key, value)
    return context


def _normalise_conditions(conditions: Optional[Iterable[str] | str]) -> Tuple[str, ...]:
    if conditions is None:
        return tuple()
    if isinstance(conditions, str):
        raw = [conditions]
    else:
        raw = list(conditions)
    result: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        cleaned = entry.strip()
        if cleaned:
            result.append(cleaned)
    return tuple(result)


def _build_tween(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    tween = dict(DEFAULT_TWEEN)
    if not isinstance(payload, Mapping):
        return tween
    kind_value = payload.get("kind") or payload.get("type")
    if isinstance(kind_value, str):
        candidate = kind_value.strip().lower()
        if candidate not in TWEEN_KINDS:
            raise ValueError(f"unsupported tween kind '{kind_value}'")
        tween["kind"] = candidate
    if "duration" in payload:
        tween["duration"] = max(
            MIN_TWEEN_DURATION,
            min(
                MAX_TWEEN_DURATION,
                _coerce_float(payload.get("duration", tween["duration"])),
            ),
        )
    if "ease" in payload and isinstance(payload["ease"], str):
        tween["ease"] = payload["ease"]
    if "hold" in payload:
        tween["hold"] = max(0.0, _coerce_float(payload.get("hold", tween["hold"])))
    if "stop_at_end" in payload:
        tween["stop_at_end"] = bool(payload["stop_at_end"])
    if "loop" in payload:
        tween["loop"] = bool(payload["loop"])
    parameters = payload.get("parameters")
    if isinstance(parameters, Mapping):
        tween["parameters"] = {
            key: parameters[key] for key in parameters if isinstance(key, str)
        }
    else:
        tween.pop("parameters", None)
    return tween


class PropManager:
    """In-memory registry for ensured props and deterministic attachment utilities."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._props: Dict[str, _EnsuredProp] = {}
        self._condition_whitelist: List[str] = list(CONDITION_WHITELIST)

    @property
    def anchors(self) -> Dict[str, Dict[str, Any]]:
        return {key: dict(cfg) for key, cfg in ANCHORS.items()}

    @property
    def condition_whitelist(self) -> Tuple[str, ...]:
        return tuple(self._condition_whitelist)

    def register_condition_variable(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("condition variable name must be a non-empty string")
        value = name.strip()
        with self._lock:
            if value not in self._condition_whitelist:
                self._condition_whitelist.append(value)

    def ensure_prop(
        self,
        prop_id: Any,
        asset: Any,
        *,
        style: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        checksum: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        generator: Optional[str] = None,
        alpha_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        prop_key = _coerce_prop_id(prop_id)
        if not isinstance(asset, str) or not asset.strip():
            raise ValueError("asset must be a non-empty string")
        asset_path = asset.strip()
        style_value = style.strip() if isinstance(style, str) else None
        tag_values = _coerce_tags(tags)
        metadata_payload = _serialise_metadata(metadata)
        generator_value = _coerce_generator(generator)
        alpha_value = _coerce_alpha_mode(alpha_mode)
        digest = _digest_payload(
            prop_key,
            asset_path,
            style_value,
            tag_values,
            checksum,
            metadata_payload,
            generator_value,
            alpha_value,
        )
        thumbnail = _build_thumbnail(digest)
        sidecar = {
            "prop_id": prop_key,
            "asset": asset_path,
            "style": style_value,
            "tags": list(tag_values),
            "thumbnail": thumbnail,
            "metadata": metadata_payload,
            "render": {
                "generator": generator_value,
                "alpha_mode": alpha_value,
            },
        }
        provenance = {
            "ensured_at": _now_iso(),
            "digest": digest,
            "source": "props.ensure_prop",
            "generator": generator_value,
        }

        with self._lock:
            existing = self._props.get(prop_key)
            if existing and existing.checksum == digest:
                return {
                    "prop": {
                        "id": existing.prop_id,
                        "asset": existing.asset,
                        "style": existing.style,
                        "tags": list(existing.tags),
                    },
                    "sidecar": dict(existing.sidecar),
                    "thumbnail": existing.thumbnail,
                    "provenance": dict(existing.provenance),
                    "deduped": True,
                }
            record = _EnsuredProp(
                prop_id=prop_key,
                checksum=digest,
                asset=asset_path,
                style=style_value,
                tags=tag_values,
                thumbnail=thumbnail,
                sidecar=sidecar,
                provenance=provenance,
                generator=generator_value,
                alpha_mode=alpha_value,
            )
            self._props[prop_key] = record
            return {
                "prop": {
                    "id": record.prop_id,
                    "asset": record.asset,
                    "style": record.style,
                    "tags": list(record.tags),
                },
                "sidecar": dict(record.sidecar),
                "thumbnail": record.thumbnail,
                "provenance": dict(record.provenance),
                "deduped": False,
            }

    def list_props(self) -> List[Dict[str, Any]]:
        with self._lock:
            records = list(self._props.values())
        return [
            {
                "prop": {
                    "id": record.prop_id,
                    "asset": record.asset,
                    "style": record.style,
                    "tags": list(record.tags),
                },
                "thumbnail": record.thumbnail,
                "sidecar": dict(record.sidecar),
                "provenance": dict(record.provenance),
                "alpha_mode": record.alpha_mode,
                "generator": record.generator,
            }
            for record in records
        ]

    def remove_prop(self, prop_id: Any) -> Optional[Dict[str, Any]]:
        prop_key = _coerce_prop_id(prop_id)
        with self._lock:
            record = self._props.pop(prop_key, None)
        if not record:
            return None
        return {
            "prop": {
                "id": record.prop_id,
                "asset": record.asset,
                "style": record.style,
                "tags": list(record.tags),
            },
            "thumbnail": record.thumbnail,
            "sidecar": dict(record.sidecar),
            "provenance": dict(record.provenance),
            "alpha_mode": record.alpha_mode,
            "generator": record.generator,
            "removed_at": _now_iso(),
        }

    def apply_prop(
        self,
        prop_id: Any,
        anchor: Any,
        *,
        z_order: Optional[str] = None,
        conditions: Optional[Iterable[str] | str] = None,
        tween: Optional[Mapping[str, Any]] = None,
        state: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        prop_key = _coerce_prop_id(prop_id)
        anchor_key = _coerce_prop_id(anchor).lower()
        if anchor_key not in ANCHORS:
            raise ValueError(f"unsupported anchor '{anchor}'")
        z_value = (z_order or "over_portrait").strip().lower()
        if z_value not in Z_ORDER_VALUES:
            raise ValueError(f"unsupported z_order '{z_order}'")

        condition_list = _normalise_conditions(conditions)
        with self._lock:
            allowed_names = tuple(self._condition_whitelist)
        context = _build_context(state, allowed_names)
        evaluations: Dict[str, bool] = {}
        for expression in condition_list:
            evaluations[expression] = _evaluate_condition(
                expression, context, allowed_names
            )
        visible = all(evaluations.values()) if evaluations else True

        tween_payload = _build_tween(tween)
        if visible:
            tween_payload["stop_at_end"] = tween_payload.get("stop_at_end", True)

        with self._lock:
            record = self._props.get(prop_key)

        response: Dict[str, Any] = {
            "prop_id": prop_key,
            "anchor": {"id": anchor_key, **ANCHORS[anchor_key]},
            "z_order": z_value,
            "visible": visible,
            "conditions": list(condition_list),
            "evaluations": evaluations,
            "tween": tween_payload,
            "applied_at": _now_iso(),
            "context": {key: context[key] for key in sorted(context)},
        }
        if record:
            response["sidecar"] = dict(record.sidecar)
            response["thumbnail"] = record.thumbnail
            response["provenance"] = dict(record.provenance)
        else:
            response["sidecar"] = None
            response["thumbnail"] = None
        return response

    def clear(self) -> None:
        with self._lock:
            self._props.clear()
            self._condition_whitelist = list(CONDITION_WHITELIST)


__all__ = [
    "ANCHORS",
    "Z_ORDER_VALUES",
    "DEFAULT_TWEEN",
    "PropManager",
    "TWEEN_KINDS",
    "ALPHA_MODES",
]
