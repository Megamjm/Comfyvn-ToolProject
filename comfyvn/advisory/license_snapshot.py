"""Utilities for capturing license/EULA snapshots and recording acknowledgements."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional

try:  # httpx is listed in requirements but keep the import defensive.
    import httpx  # type: ignore
except Exception:  # pragma: no cover - optional dependency guard
    httpx = None  # type: ignore

from comfyvn.core import modder_hooks
from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger("comfyvn.advisory.license_snapshot")

SETTINGS_KEY = "advisory_licenses"
DEFAULT_MAX_BYTES = 1_000_000  # 1 MB upper bound for fetched license text

_SETTINGS = SettingsManager()


class LicenseSnapshotError(RuntimeError):
    """Raised when a license snapshot operation fails."""


class LicenseAcknowledgementRequired(LicenseSnapshotError):
    """Raised when an acknowledgement is required for the requested asset."""


def _timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    trimmed = [line.rstrip() for line in lines]
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    return "\n".join(trimmed)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(value: str) -> str:
    keep = []
    for ch in value.strip().lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in (".", "-", "_"):
            keep.append(ch)
        else:
            keep.append("_")
    slug = "".join(keep).strip("_")
    return slug or "asset"


def _target_dir(asset_path: Optional[Path], asset_id: str) -> Path:
    if asset_path is not None:
        if asset_path.is_dir():
            return asset_path
        return asset_path.parent
    slug = _slugify(asset_id)
    return Path("data") / "license_snapshots" / slug


def _load_settings_registry() -> Dict[str, Any]:
    cfg = _SETTINGS.load()
    raw = cfg.get(SETTINGS_KEY)
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _save_settings_registry(registry: Mapping[str, Any]) -> None:
    cfg = _SETTINGS.load()
    cfg[SETTINGS_KEY] = dict(registry)
    _SETTINGS.save(cfg)


def _load_snapshot_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise LicenseSnapshotError(f"Snapshot file missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise LicenseSnapshotError(f"Failed to read snapshot {path}: {exc}") from exc


def _write_snapshot_file(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _emit_hook(event: str, payload: Mapping[str, Any]) -> None:
    try:
        modder_hooks.emit(event, dict(payload))
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Modder hook emission failed for %s", event, exc_info=True)


def _fetch_text(
    url: str, *, timeout: float = 10.0, max_bytes: int = DEFAULT_MAX_BYTES
) -> str:
    if httpx is None:  # pragma: no cover - optional dependency guard
        raise LicenseSnapshotError("httpx is required to fetch license text.")
    headers = {
        "User-Agent": "ComfyVN-LicenseSnapshot/1.0",
        "Accept": "text/plain, text/*;q=0.9, */*;q=0.1",
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content = response.content
            if len(content) > max_bytes:
                raise LicenseSnapshotError(
                    f"License text at {url} exceeds {max_bytes} bytes limit."
                )
            return response.text
    except LicenseSnapshotError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise LicenseSnapshotError(
            f"Failed to fetch license text from {url}: {exc}"
        ) from exc


@dataclass
class SnapshotResult:
    ok: bool
    asset_id: str
    hash: str
    captured_at: str
    snapshot_path: str
    requires_ack: bool
    acknowledgements: Dict[str, Any]
    text: str
    source_url: Optional[str]
    metadata: Dict[str, Any]


def capture_snapshot(
    asset_id: str,
    *,
    asset_path: Optional[str | os.PathLike[str]] = None,
    snapshot_dir: Optional[str | os.PathLike[str]] = None,
    source_url: Optional[str] = None,
    text: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    user: Optional[str] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> SnapshotResult:
    """
    Capture (or refresh) a license snapshot for ``asset_id`` and persist it to disk.

    Returns a structured ``SnapshotResult`` with acknowledgement state so callers can
    prompt users before continuing with risky downloads.
    """

    if not asset_id or not str(asset_id).strip():
        raise LicenseSnapshotError("asset_id is required for license snapshots.")

    asset_path_obj = Path(asset_path).expanduser() if asset_path else None
    snapshot_dir_obj = Path(snapshot_dir).expanduser() if snapshot_dir else None
    target_dir = snapshot_dir_obj or _target_dir(asset_path_obj, asset_id)
    snapshot_path = target_dir / "license_snapshot.json"

    if text is None:
        if not source_url:
            raise LicenseSnapshotError("source_url required when text is omitted.")
        text = _fetch_text(source_url, max_bytes=max_bytes)

    normalized_text = _normalize_text(text)
    digest = _text_hash(normalized_text)
    captured_at = _timestamp()
    metadata_dict: Dict[str, Any] = dict(metadata or {})

    existing_ack: Iterable[Mapping[str, Any]]
    existing_ack = ()
    if snapshot_path.exists():
        previous = _load_snapshot_file(snapshot_path)
        prev_hash = previous.get("hash", {}).get("value")
        acknowledgements = previous.get("acknowledgements")
        if isinstance(acknowledgements, Iterable) and prev_hash == digest:
            existing_ack = acknowledgements  # type: ignore[assignment]
        else:
            existing_ack = []
    ack_payload = [dict(entry) for entry in existing_ack if isinstance(entry, Mapping)]

    payload = {
        "asset_id": asset_id,
        "asset_path": str(asset_path_obj.as_posix()) if asset_path_obj else None,
        "snapshot_path": snapshot_path.as_posix(),
        "source": {
            "url": source_url,
        },
        "hash": {"algorithm": "sha256", "value": digest},
        "captured_at": captured_at,
        "text": normalized_text,
        "metadata": metadata_dict,
        "acknowledgements": ack_payload,
    }
    _write_snapshot_file(snapshot_path, payload)

    registry = _load_settings_registry()
    entry: MutableMapping[str, Any] = dict(registry.get(asset_id, {}))
    ack_by_user: MutableMapping[str, Any]
    ack_by_user = dict(entry.get("ack_by_user") or {})
    if entry.get("hash") != digest:
        ack_by_user = {}
    entry.update(
        {
            "asset_id": asset_id,
            "asset_path": str(asset_path_obj.as_posix()) if asset_path_obj else None,
            "snapshot_path": snapshot_path.as_posix(),
            "hash": digest,
            "source_url": source_url,
            "captured_at": captured_at,
            "metadata": metadata_dict,
            "ack_by_user": ack_by_user,
        }
    )
    registry[asset_id] = entry
    _save_settings_registry(registry)

    if user:
        LOGGER.info("License snapshot refreshed for %s by %s", asset_id, user)
    else:
        LOGGER.info("License snapshot refreshed for %s", asset_id)

    _emit_hook(
        "on_asset_meta_updated",
        {
            "uid": asset_id,
            "path": entry.get("asset_path"),
            "meta": {
                "license_snapshot": {
                    "hash": digest,
                    "captured_at": captured_at,
                    "source_url": source_url,
                }
            },
            "sidecar": None,
            "bytes": None,
        },
    )

    requires_ack = not ack_by_user
    return SnapshotResult(
        ok=True,
        asset_id=asset_id,
        hash=digest,
        captured_at=captured_at,
        snapshot_path=snapshot_path.as_posix(),
        requires_ack=requires_ack,
        acknowledgements=dict(ack_by_user),
        text=normalized_text,
        source_url=source_url,
        metadata=metadata_dict,
    )


def status(asset_id: str, *, include_text: bool = False) -> Dict[str, Any]:
    """Return acknowledgement status for ``asset_id``. Includes text when requested."""

    if not asset_id:
        raise LicenseSnapshotError("asset_id is required")

    registry = _load_settings_registry()
    entry = registry.get(asset_id)
    if not isinstance(entry, Mapping):
        raise LicenseSnapshotError(f"No snapshot stored for asset '{asset_id}'")

    snapshot_path = entry.get("snapshot_path")
    text_payload = None
    if include_text and snapshot_path:
        try:
            file_data = _load_snapshot_file(Path(snapshot_path))
        except LicenseSnapshotError as exc:
            LOGGER.warning("Failed reading snapshot for %s: %s", asset_id, exc)
            file_data = None
        if isinstance(file_data, Mapping):
            text_payload = file_data.get("text")

    ack_by_user = entry.get("ack_by_user")
    if not isinstance(ack_by_user, Mapping):
        ack_by_user = {}

    state = {
        "asset_id": asset_id,
        "hash": entry.get("hash"),
        "source_url": entry.get("source_url"),
        "captured_at": entry.get("captured_at"),
        "snapshot_path": snapshot_path,
        "metadata": entry.get("metadata") or {},
        "acknowledgements": dict(ack_by_user),
        "requires_ack": not ack_by_user,
    }
    if include_text and text_payload is not None:
        state["text"] = text_payload
    return state


def require_ack(asset_id: str, *, hash_value: Optional[str] = None) -> Dict[str, Any]:
    """Raise ``LicenseAcknowledgementRequired`` when a matching acknowledgement is absent."""

    info = status(asset_id, include_text=False)
    ack_map = info.get("acknowledgements") or {}
    if hash_value and info.get("hash") and hash_value != info.get("hash"):
        raise LicenseAcknowledgementRequired(
            f"Snapshot hash mismatch for {asset_id}; ack must target hash {info.get('hash')}."
        )
    if not ack_map:
        raise LicenseAcknowledgementRequired(
            f"Licence acknowledgement required for asset '{asset_id}'."
        )
    if hash_value:
        matching = [
            k
            for k, v in ack_map.items()
            if isinstance(v, Mapping) and v.get("hash") == hash_value
        ]
        if not matching:
            raise LicenseAcknowledgementRequired(
                f"Acknowledgement for asset '{asset_id}' does not cover hash {hash_value}."
            )
    return info


def record_ack(
    asset_id: str,
    *,
    user: str,
    asset_path: Optional[str | os.PathLike[str]] = None,
    source_url: Optional[str] = None,
    hash_value: Optional[str] = None,
    notes: Optional[str] = None,
    provenance: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist an acknowledgement for ``asset_id`` and return the updated status."""

    if not user or not str(user).strip():
        raise LicenseSnapshotError("user is required for acknowledgements.")

    registry = _load_settings_registry()
    entry = registry.get(asset_id)
    if not isinstance(entry, MutableMapping):
        raise LicenseSnapshotError(f"No snapshot recorded for asset '{asset_id}'.")

    snapshot_path = entry.get("snapshot_path")
    if not snapshot_path:
        raise LicenseSnapshotError(f"Snapshot path unknown for asset '{asset_id}'.")

    file_data = _load_snapshot_file(Path(snapshot_path))
    snapshot_hash = (
        file_data.get("hash", {}).get("value")
        if isinstance(file_data, Mapping)
        else None
    )
    if not snapshot_hash:
        raise LicenseSnapshotError(f"Snapshot hash missing for asset '{asset_id}'.")

    if hash_value and hash_value != snapshot_hash:
        raise LicenseSnapshotError(
            f"Provided hash {hash_value} does not match stored snapshot hash for '{asset_id}'."
        )
    hash_value = snapshot_hash

    ack_entry = {
        "user": user,
        "hash": hash_value,
        "acknowledged_at": _timestamp(),
        "notes": notes,
        "source_url": source_url or entry.get("source_url"),
        "provenance": dict(provenance or {}),
    }

    ack_by_user = dict(entry.get("ack_by_user") or {})
    ack_by_user[user] = ack_entry
    entry["ack_by_user"] = ack_by_user
    if asset_path:
        entry["asset_path"] = Path(asset_path).expanduser().as_posix()
    if source_url:
        entry["source_url"] = source_url
    registry[asset_id] = entry
    _save_settings_registry(registry)

    acknowledgements = file_data.get("acknowledgements")
    ack_list: list[Dict[str, Any]] = []
    if isinstance(acknowledgements, list):
        ack_list = [
            dict(item) for item in acknowledgements if isinstance(item, Mapping)
        ]
    # Replace or append acknowledgement for the user.
    replaced = False
    for idx, item in enumerate(ack_list):
        if item.get("user") == user:
            ack_list[idx] = dict(ack_entry)
            replaced = True
            break
    if not replaced:
        ack_list.append(dict(ack_entry))
    file_data["acknowledgements"] = ack_list
    _write_snapshot_file(Path(snapshot_path), file_data)

    _emit_hook(
        "on_asset_meta_updated",
        {
            "uid": asset_id,
            "path": entry.get("asset_path"),
            "meta": {
                "license_ack": {
                    "user": user,
                    "hash": hash_value,
                    "acknowledged_at": ack_entry["acknowledged_at"],
                    "provenance": ack_entry.get("provenance"),
                }
            },
            "sidecar": None,
            "bytes": None,
        },
    )

    LOGGER.info("License ack recorded for %s by %s", asset_id, user)
    return status(asset_id, include_text=False)


__all__ = [
    "LicenseAcknowledgementRequired",
    "LicenseSnapshotError",
    "SnapshotResult",
    "capture_snapshot",
    "record_ack",
    "require_ack",
    "status",
]
