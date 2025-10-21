from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional

__all__ = [
    "Savepoint",
    "SavepointError",
    "SavepointNotFound",
    "load_slot",
    "list_slots",
    "sanitize_slot",
    "save_slot",
]


SAVE_DIR = Path("data/saves")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

_SANITIZE_RE = re.compile(r"[^a-z0-9_-]+")
_RESERVED_KEYS = {"slot", "saved_at", "saved_at_iso", "vars", "node_pointer", "seed"}


class SavepointError(RuntimeError):
    """Raised when a savepoint operation fails."""


class SavepointNotFound(SavepointError):
    """Raised when attempting to load a non-existent savepoint slot."""


@dataclass(frozen=True)
class Savepoint:
    slot: str
    saved_at: int
    saved_at_iso: str
    vars: Dict[str, Any]
    node_pointer: Any
    seed: Any
    extras: Dict[str, Any]
    path: Path

    def payload(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "slot": self.slot,
            "saved_at": self.saved_at,
            "saved_at_iso": self.saved_at_iso,
            "vars": json.loads(json.dumps(self.vars)),
            "node_pointer": self.node_pointer,
            "seed": self.seed,
        }
        for key, value in self.extras.items():
            data[key] = value
        return data

    def summary(self) -> Dict[str, Any]:
        size = self.path.stat().st_size if self.path.exists() else None
        return {
            "slot": self.slot,
            "saved_at": self.saved_at,
            "saved_at_iso": self.saved_at_iso,
            "size_bytes": size,
        }


def sanitize_slot(slot: str) -> str:
    if not isinstance(slot, str):
        raise SavepointError("slot must be a string")
    trimmed = slot.strip().lower()
    trimmed = trimmed.replace(" ", "-")
    sanitized = _SANITIZE_RE.sub("-", trimmed)
    sanitized = sanitized.strip("-_")
    if not sanitized:
        raise SavepointError("slot cannot be empty")
    if len(sanitized) > 80:
        sanitized = sanitized[:80]
    return sanitized


def list_slots() -> List[Savepoint]:
    savepoints: List[Savepoint] = []
    for path in SAVE_DIR.glob("*.json"):
        try:
            savepoints.append(_load_from_path(path))
        except SavepointError:
            continue
    savepoints.sort(key=lambda item: item.saved_at, reverse=True)
    return savepoints


def load_slot(slot: str) -> Savepoint:
    sanitized = sanitize_slot(slot)
    path = _slot_path(sanitized)
    if not path.exists():
        raise SavepointNotFound(f"save slot not found: {sanitized}")
    return _load_from_path(path)


def save_slot(slot: str, payload: Mapping[str, Any]) -> Savepoint:
    sanitized = sanitize_slot(slot)
    state = _expect_mapping(payload)

    vars_payload = state.get("vars")
    if not isinstance(vars_payload, Mapping):
        raise SavepointError("save payload must include dict 'vars'")
    vars_dict = json.loads(json.dumps(vars_payload))

    node_pointer = state.get("node_pointer")
    seed = state.get("seed")

    extras = _collect_extras(state)

    saved_at, saved_at_iso = _timestamp()

    record: Dict[str, Any] = {
        "slot": sanitized,
        "saved_at": saved_at,
        "saved_at_iso": saved_at_iso,
        "vars": vars_dict,
        "node_pointer": node_pointer,
        "seed": seed,
    }
    record.update(extras)

    encoded = _encode_json(record)
    path = _slot_path(sanitized)
    _write_atomic(path, encoded)

    return Savepoint(
        slot=sanitized,
        saved_at=saved_at,
        saved_at_iso=saved_at_iso,
        vars=vars_dict,
        node_pointer=node_pointer,
        seed=seed,
        extras=extras,
        path=path,
    )


def _collect_extras(state: Mapping[str, Any]) -> Dict[str, Any]:
    extras: Dict[str, Any] = {}
    for key, value in state.items():
        if key in {"vars", "node_pointer", "seed"}:
            continue
        extras[key] = value
    return extras


def _expect_mapping(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise SavepointError("save payload must be a mapping")
    return payload


def _slot_path(slot: str) -> Path:
    return SAVE_DIR / f"{slot}.json"


def _timestamp(now: Optional[float] = None) -> tuple[int, str]:
    dt = (
        datetime.now(timezone.utc)
        if now is None
        else datetime.fromtimestamp(now, tz=timezone.utc)
    )
    ms = int(dt.timestamp() * 1000)
    iso = dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return ms, iso


def _encode_json(record: Dict[str, Any]) -> str:
    try:
        return json.dumps(record, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise SavepointError(f"save payload not serializable: {exc}") from exc


def _write_atomic(path: Path, encoded: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent), delete=False
    ) as tmp:
        tmp.write(encoded)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _load_from_path(path: Path) -> Savepoint:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SavepointNotFound(f"save slot missing: {path.stem}") from exc
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SavepointError(f"save slot corrupt: {path.name}") from exc
    if not isinstance(record, dict):
        raise SavepointError(f"save slot invalid: {path.name}")

    saved_at = _coerce_int(record.get("saved_at"), int(path.stat().st_mtime * 1000))
    saved_at_iso = record.get("saved_at_iso")
    if not isinstance(saved_at_iso, str) or not saved_at_iso:
        saved_at_iso = _timestamp(saved_at / 1000.0)[1]

    vars_payload = record.get("vars")
    if isinstance(vars_payload, Mapping):
        vars_dict = json.loads(json.dumps(vars_payload))
    else:
        vars_dict = {}

    node_pointer = record.get("node_pointer")
    seed = record.get("seed")

    extras: Dict[str, Any] = {}
    for key, value in record.items():
        if key in _RESERVED_KEYS:
            continue
        extras[key] = value

    slot_value = record.get("slot")
    if isinstance(slot_value, str) and slot_value.strip():
        try:
            slot = sanitize_slot(slot_value)
        except SavepointError:
            slot = path.stem
    else:
        slot = path.stem

    return Savepoint(
        slot=slot,
        saved_at=saved_at,
        saved_at_iso=saved_at_iso,
        vars=vars_dict,
        node_pointer=node_pointer,
        seed=seed,
        extras=extras,
        path=path,
    )


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default
