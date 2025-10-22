"""
Minimal telemetry collection with privacy safeguards.

Telemetry is strictly opt-in via ``config/comfyvn.json`` and only stores
aggregated counts plus anonymised event metadata. Crash uploads are gated
separately and rely on the anonymiser to scrub identifiers before they ever
leave the machine.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from zipfile import ZIP_DEFLATED, ZipFile

from comfyvn.config import feature_flags
from comfyvn.config.runtime_paths import config_dir, diagnostics_dir, logs_dir
from comfyvn.obs.anonymize import (
    anonymize_payload,
    anonymous_installation_id,
    hash_identifier,
)

TELEMETRY_FEATURE_FLAG = "enable_privacy_telemetry"
CRASH_UPLOADS_FEATURE_FLAG = "enable_crash_uploader"

_CONFIG_CANDIDATES: tuple[Path, ...] = (
    Path("comfyvn.json"),
    Path("config/comfyvn.json"),
)


@dataclass(frozen=True)
class TelemetrySettings:
    telemetry_opt_in: bool = False
    crash_opt_in: bool = False
    diagnostics_opt_in: bool = False
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "telemetry_opt_in": bool(self.telemetry_opt_in),
            "crash_opt_in": bool(self.crash_opt_in),
            "diagnostics_opt_in": bool(self.diagnostics_opt_in),
            "dry_run": bool(self.dry_run),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "TelemetrySettings":
        if not isinstance(payload, Mapping):
            return cls()
        return cls(
            telemetry_opt_in=bool(payload.get("telemetry_opt_in", False)),
            crash_opt_in=bool(payload.get("crash_opt_in", False)),
            diagnostics_opt_in=bool(payload.get("diagnostics_opt_in", False)),
            dry_run=bool(payload.get("dry_run", True)),
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def load_settings() -> TelemetrySettings:
    merged: dict[str, Any] = {}
    for path in _CONFIG_CANDIDATES:
        data = _read_json(path)
        section = data.get("telemetry")
        if isinstance(section, Mapping):
            merged.update(section)
    return TelemetrySettings.from_dict(merged)


def persist_settings(settings: TelemetrySettings) -> None:
    payload = _read_json(_CONFIG_CANDIDATES[-1])
    payload["telemetry"] = settings.to_dict()
    target = _CONFIG_CANDIDATES[-1]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _state_path() -> Path:
    return logs_dir("telemetry", "usage.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryStore:
    """Thread-safe store for anonymised telemetry counters."""

    def __init__(self, *, app_version: str | None = None) -> None:
        self._lock = threading.Lock()
        self._settings = load_settings()
        self._state = self._load_state()
        self._state.setdefault("anonymous_id", anonymous_installation_id())
        if app_version:
            self._state.setdefault("app_version", app_version)
        self._persist_state()

    # ------------------------------------------------------------------ helpers
    def _load_state(self) -> dict[str, Any]:
        path = _state_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return {
            "features": {},
            "events": [],
            "hooks": {},
            "meta": {"created_at": _utc_now()},
        }

    def _persist_state(self) -> None:
        with self._lock:
            self._persist_state_locked()

    def _persist_state_locked(self) -> None:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def _settings_updated(self) -> None:
        with self._lock:
            meta = self._state.setdefault("meta", {})
            meta["settings_updated_at"] = _utc_now()
            self._persist_state_locked()

    def _ensure_app_version(self, version: str | None) -> None:
        if not version:
            return
        with self._lock:
            if self._state.get("app_version") != version:
                self._state["app_version"] = version
                self._persist_state_locked()

    # ------------------------------------------------------------------ settings
    @property
    def settings(self) -> TelemetrySettings:
        return self._settings

    def refresh_settings(self) -> TelemetrySettings:
        self._settings = load_settings()
        return self._settings

    def update_settings(
        self,
        *,
        telemetry_opt_in: Optional[bool] = None,
        crash_opt_in: Optional[bool] = None,
        diagnostics_opt_in: Optional[bool] = None,
        dry_run: Optional[bool] = None,
    ) -> TelemetrySettings:
        settings_dict = self._settings.to_dict()
        if telemetry_opt_in is not None:
            settings_dict["telemetry_opt_in"] = bool(telemetry_opt_in)
        if crash_opt_in is not None:
            settings_dict["crash_opt_in"] = bool(crash_opt_in)
        if diagnostics_opt_in is not None:
            settings_dict["diagnostics_opt_in"] = bool(diagnostics_opt_in)
        if dry_run is not None:
            settings_dict["dry_run"] = bool(dry_run)
        self._settings = TelemetrySettings.from_dict(settings_dict)
        persist_settings(self._settings)
        self._settings_updated()
        return self._settings

    # ------------------------------------------------------------------ status
    @property
    def anonymous_id(self) -> str:
        return str(self._state.get("anonymous_id") or anonymous_installation_id())

    def telemetry_allowed(self) -> bool:
        if not feature_flags.is_enabled(TELEMETRY_FEATURE_FLAG):
            return False
        return bool(self._settings.telemetry_opt_in)

    def crash_uploads_allowed(self) -> bool:
        if not feature_flags.is_enabled(CRASH_UPLOADS_FEATURE_FLAG):
            return False
        return bool(self._settings.crash_opt_in)

    def diagnostics_allowed(self) -> bool:
        return bool(self._settings.diagnostics_opt_in)

    # ------------------------------------------------------------------ recorders
    def record_feature(self, name: str, *, variant: str | None = None) -> bool:
        if not self.telemetry_allowed():
            return False
        safe_name = str(name).strip().lower()
        if not safe_name:
            return False
        now = _utc_now()
        with self._lock:
            features = self._state.setdefault("features", {})
            record = features.setdefault(
                safe_name,
                {"total": 0, "last_ts": now},
            )
            record["total"] = int(record.get("total", 0)) + 1
            record["last_ts"] = now
            if variant:
                safe_variant = str(variant).strip().lower()
                variants = record.setdefault("variants", {})
                variants[safe_variant] = int(variants.get(safe_variant, 0)) + 1
            self._persist_state_locked()
        return True

    def record_event(
        self,
        event: str,
        payload: Mapping[str, Any] | None = None,
        *,
        category: str = "custom",
    ) -> bool:
        if not self.telemetry_allowed():
            return False
        safe_event = str(event).strip().lower()
        if not safe_event:
            return False
        sanitized = anonymize_payload(payload or {})
        entry = {
            "event": safe_event,
            "category": category,
            "ts": _utc_now(),
            "payload": sanitized,
        }
        with self._lock:
            events = self._state.setdefault("events", [])
            events.append(entry)
            if len(events) > 200:
                del events[: len(events) - 200]
            self._persist_state_locked()
        return True

    def record_hook_event(self, hook_name: str, payload: Mapping[str, Any]) -> bool:
        if not self.telemetry_allowed():
            return False
        safe_hook = str(hook_name).strip().lower()
        if not safe_hook:
            return False
        now = _utc_now()
        with self._lock:
            hooks = self._state.setdefault("hooks", {})
            entry = hooks.setdefault(
                safe_hook,
                {
                    "total": 0,
                    "last_ts": now,
                },
            )
            entry["total"] = int(entry.get("total", 0)) + 1
            entry["last_ts"] = now
            sample = anonymize_payload(dict(payload))
            entry.setdefault("samples", [])
            samples: list[dict[str, Any]] = entry["samples"]
            samples.append({"ts": now, "payload": sample})
            if len(samples) > 5:
                del samples[: len(samples) - 5]
            self._persist_state_locked()
        return True

    def register_crash_report(self, report_path: Path) -> bool:
        if not self.crash_uploads_allowed():
            return False
        now = _utc_now()
        digest = hash_identifier(str(report_path), namespace="crash.report")
        with self._lock:
            crashes = self._state.setdefault("crashes", [])
            crashes.append({"report": digest, "ts": now})
            if len(crashes) > 50:
                del crashes[: len(crashes) - 50]
            self._persist_state_locked()
        return True

    # ------------------------------------------------------------------ export & summary
    def summary(self, *, include_events: bool = False) -> dict[str, Any]:
        with self._lock:
            features = dict(self._state.get("features") or {})
            hooks = dict(self._state.get("hooks") or {})
            meta = dict(self._state.get("meta") or {})
            crashes = list(self._state.get("crashes") or [])
            events = list(self._state.get("events") or []) if include_events else []
            app_version = self._state.get("app_version") or os.getenv(
                "COMFYVN_VERSION", "unknown"
            )
        return {
            "anonymous_id": self.anonymous_id,
            "app_version": app_version,
            "telemetry_active": self.telemetry_allowed(),
            "crash_uploads_active": self.crash_uploads_allowed(),
            "diagnostics_opt_in": self.diagnostics_allowed(),
            "dry_run": bool(self._settings.dry_run),
            "features": features,
            "hooks": hooks,
            "crashes": crashes,
            "events": events,
            "meta": meta,
        }

    def export_bundle(self, *, limit_crash_reports: int = 10) -> Path:
        now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        anon_slug = self.anonymous_id[:8]
        filename = f"comfyvn-diagnostics-{now}-{anon_slug}.zip"
        bundle_path = diagnostics_dir(filename)

        manifest = {
            "generated_at": _utc_now(),
            "anonymous_id": self.anonymous_id,
            "app_version": self._state.get("app_version")
            or os.getenv("COMFYVN_VERSION", "unknown"),
            "telemetry_active": self.telemetry_allowed(),
            "crash_uploads_active": self.crash_uploads_allowed(),
            "diagnostics_opt_in": self.diagnostics_allowed(),
        }

        snapshot = self.summary(include_events=True)
        crash_summary = _summarize_crash_reports(limit=limit_crash_reports)

        with ZipFile(bundle_path, "w", ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("telemetry.json", json.dumps(snapshot, indent=2))
            zf.writestr("crashes.json", json.dumps(crash_summary, indent=2))

        return bundle_path


def _summarize_crash_reports(limit: int = 10) -> list[dict[str, Any]]:
    try:
        from comfyvn.obs.crash_reporter import iter_reports
    except Exception:
        return []
    reports = list(iter_reports(limit=limit))
    sanitized: list[dict[str, Any]] = []
    for report in reports:
        sanitized.append(
            {
                "event_id": report.get("event_id"),
                "timestamp": report.get("timestamp"),
                "exc_type": report.get("exc_type"),
                "message_digest": hash_identifier(
                    report.get("message", ""),
                    namespace="crash.message",
                ),
            }
        )
    return sanitized


_TELEMETRY_SINGLETON: TelemetryStore | None = None
_TELEMETRY_LOCK = threading.Lock()


def get_telemetry(app_version: str | None = None) -> TelemetryStore:
    global _TELEMETRY_SINGLETON
    with _TELEMETRY_LOCK:
        if _TELEMETRY_SINGLETON is None:
            _TELEMETRY_SINGLETON = TelemetryStore(app_version=app_version)
        else:
            _TELEMETRY_SINGLETON._ensure_app_version(app_version)
        return _TELEMETRY_SINGLETON


__all__ = [
    "TelemetrySettings",
    "TelemetryStore",
    "get_telemetry",
    "load_settings",
    "persist_settings",
]
