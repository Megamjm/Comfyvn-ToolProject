"""Session context synchronisation with SillyTavern.

This module prepares VN session state into a compact payload and relays it to
the `comfyvn-data-exporter` SillyTavern plugin.  The plugin can then enrich the
conversation, provide assistant replies, or mirror state back into the
SillyTavern UI.  The interface is intentionally lightweight so unit tests can
inject mock transports or operate in dry-run mode without reaching a live
SillyTavern instance.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

import requests

from comfyvn.core.scene_store import SceneStore
from comfyvn.core.settings_manager import SettingsManager

try:  # pragma: no cover - SillyTavern bridge may be unavailable on CI
    from comfyvn.integrations.sillytavern_bridge import (
        SillyTavernBridge,
        SillyTavernBridgeError,
    )
except Exception:  # pragma: no cover - degraded mode for headless tests
    SillyTavernBridge = None  # type: ignore

    class SillyTavernBridgeError(RuntimeError):
        """Fallback error when the SillyTavern bridge helper cannot be imported."""


LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 2.0
DEFAULT_MESSAGE_LIMIT = 50
_SCENE_STORE = SceneStore()


class SessionSyncError(RuntimeError):
    """Raised when session synchronisation fails."""


def _coerce_session_id(
    session_id: Optional[str],
    scene_id: Optional[str],
    node_id: Optional[str],
) -> str:
    if session_id:
        return str(session_id)
    if scene_id:
        return f"scene:{scene_id}"
    if node_id:
        return f"node:{node_id}"
    return f"session-{uuid.uuid4().hex[:12]}"


def _coerce_mapping(payload: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def normalise_messages(
    messages: Optional[Sequence[Any]],
    *,
    limit: Optional[int] = DEFAULT_MESSAGE_LIMIT,
) -> list[dict[str, Any]]:
    """Normalise arbitrary chat payloads into a consistent structure."""
    if not messages:
        return []

    normalised: list[dict[str, Any]] = []
    for entry in messages:
        if entry is None:
            continue
        if isinstance(entry, str):
            normalised.append({"role": "narration", "content": entry})
            continue
        if isinstance(entry, Mapping):
            content = entry.get("content") or entry.get("text") or entry.get("line")
            role = entry.get("role") or entry.get("speaker") or entry.get("character")
            record: dict[str, Any] = {
                "role": str(role or "narrator"),
                "content": str(content or ""),
            }
            if "timestamp" in entry and entry["timestamp"] is not None:
                record["timestamp"] = entry["timestamp"]
            meta = {
                key: value
                for key, value in entry.items()
                if key
                not in {
                    "role",
                    "speaker",
                    "character",
                    "content",
                    "text",
                    "line",
                    "timestamp",
                }
            }
            if meta:
                record["meta"] = meta
            normalised.append(record)
            continue
        normalised.append({"role": "narration", "content": str(entry)})

    if limit and limit > 0 and len(normalised) > limit:
        normalised = normalised[-limit:]
    return normalised


@dataclass(slots=True)
class SessionContext:
    """Prepared SillyTavern session payload."""

    session_id: str
    scene_id: Optional[str] = None
    node_id: Optional[str] = None
    pov: Optional[str] = None
    variables: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    scene: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None

    def as_payload(self) -> dict[str, Any]:
        payload = {
            "session_id": self.session_id,
            "scene_id": self.scene_id,
            "node_id": self.node_id,
            "pov": self.pov,
            "variables": self.variables,
            "messages": self.messages,
            "scene": self.scene,
            "metadata": self.metadata,
            "user_id": self.user_id,
        }
        # Drop ``None`` values but keep falsy values such as empty strings/lists.
        return {key: value for key, value in payload.items() if value is not None}


def build_session_context(
    *,
    session_id: Optional[str] = None,
    scene_id: Optional[str] = None,
    node_id: Optional[str] = None,
    pov: Optional[str] = None,
    variables: Optional[Mapping[str, Any]] = None,
    messages: Optional[Sequence[Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    scene: Optional[Mapping[str, Any]] = None,
    user_id: Optional[str] = None,
    limit_messages: Optional[int] = DEFAULT_MESSAGE_LIMIT,
) -> SessionContext:
    """Create a :class:`SessionContext` from loosely structured inputs."""
    context_id = _coerce_session_id(session_id, scene_id, node_id)
    message_list = normalise_messages(messages, limit=limit_messages)
    variables_map = _coerce_mapping(variables)
    meta_map = _coerce_mapping(metadata)

    if scene_id and "scene_id" not in meta_map:
        meta_map["scene_id"] = scene_id
    if node_id and "node_id" not in meta_map:
        meta_map["node_id"] = node_id
    if pov and "pov" not in meta_map:
        meta_map["pov"] = pov

    prepared_scene = dict(scene) if isinstance(scene, Mapping) else None

    return SessionContext(
        session_id=context_id,
        scene_id=scene_id,
        node_id=node_id,
        pov=pov,
        variables=variables_map,
        messages=message_list,
        scene=prepared_scene,
        metadata=meta_map,
        user_id=user_id,
    )


@dataclass(slots=True)
class SessionSyncResult:
    """Structured summary returned after a sync call."""

    ok: bool
    reply: Optional[Any]
    latency_ms: float
    sent: dict[str, Any]
    received: dict[str, Any]
    error: Optional[str] = None
    endpoint: Optional[str] = None
    timestamp: float = field(default_factory=lambda: time.time())

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": "ok" if self.ok else "error",
            "reply": self.reply,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "sent": self.sent,
            "received": self.received,
            "endpoint": self.endpoint,
            "timestamp": self.timestamp,
        }


def _build_bridge(
    *,
    settings: Optional[SettingsManager],
    base_url: Optional[str],
    plugin_base: Optional[str],
    timeout: float,
) -> SillyTavernBridge:
    if SillyTavernBridge is None:  # pragma: no cover - defensive guardrail
        raise SessionSyncError("SillyTavern bridge helper unavailable.")
    try:
        return SillyTavernBridge(
            settings=settings,
            base_url=base_url,
            plugin_base=plugin_base,
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise SessionSyncError(
            f"Failed to initialise SillyTavern bridge: {exc}"
        ) from exc


def sync_session(
    context: SessionContext,
    *,
    settings: Optional[SettingsManager] = None,
    base_url: Optional[str] = None,
    plugin_base: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> SessionSyncResult:
    """
    Send the prepared context to SillyTavern and return the reply payload.

    When ``dry_run`` is True the payload is not transmitted; instead a summary
    is returned immediately.  Errors are wrapped in :class:`SessionSyncError`
    for convenient handling by API routes.
    """
    bridge = _build_bridge(
        settings=settings,
        base_url=base_url,
        plugin_base=plugin_base,
        timeout=timeout,
    )
    endpoint = f"{bridge.base_url}{bridge.plugin_base}/session/sync"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if bridge.token:
        headers["Authorization"] = f"Bearer {bridge.token}"
    params: dict[str, Any] = {}
    if context.user_id or bridge.user_id:
        params["user_id"] = context.user_id or bridge.user_id

    payload = context.as_payload()
    start = time.perf_counter()

    if dry_run:
        latency_ms = (time.perf_counter() - start) * 1000.0
        bridge.close()
        return SessionSyncResult(
            ok=True,
            reply=None,
            latency_ms=round(latency_ms, 2),
            sent=payload,
            received={"mode": "dry_run"},
            endpoint=endpoint,
        )

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            params=params or None,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
    except SillyTavernBridgeError as exc:
        raise SessionSyncError(str(exc)) from exc
    except requests.RequestException as exc:
        raise SessionSyncError(f"Session sync request failed: {exc}") from exc
    except ValueError as exc:
        raise SessionSyncError(f"Invalid JSON from SillyTavern: {exc}") from exc
    finally:
        try:
            bridge.close()
        except Exception:  # pragma: no cover - defensive
            pass

    latency_ms = (time.perf_counter() - start) * 1000.0
    reply = body.get("reply") if isinstance(body, Mapping) else None
    ok = bool(body.get("ok", True)) if isinstance(body, Mapping) else True
    error_msg = None
    if isinstance(body, Mapping) and not ok:
        error_msg = str(body.get("error") or body.get("detail") or "")
    LOGGER.debug(
        "SillyTavern session sync (%s) → ok=%s latency=%.2fms",
        context.session_id,
        ok,
        latency_ms,
    )

    return SessionSyncResult(
        ok=ok,
        reply=reply,
        latency_ms=round(latency_ms, 2),
        sent=payload,
        received=body if isinstance(body, Mapping) else {"raw": body},
        error=error_msg or None,
        endpoint=endpoint,
    )


def load_scene_dialogue(scene_id: str) -> list[dict[str, Any]]:
    """Load dialogue lines for a SceneStore entry."""
    try:
        payload = _SCENE_STORE.load(scene_id)
    except Exception as exc:  # pragma: no cover - filesystem / JSON errors
        LOGGER.debug("Scene %s load failed: %s", scene_id, exc)
        return []
    if not isinstance(payload, Mapping):
        return []
    raw_lines = payload.get("dialogue") or payload.get("lines") or []
    lines: list[dict[str, Any]] = []
    for entry in raw_lines:
        if isinstance(entry, Mapping):
            lines.append(dict(entry))
    return lines


def _summarise_active_context(data: Mapping[str, Any]) -> str:
    parts: list[str] = []
    world = data.get("active_world")
    if world:
        parts.append(f"World: {world}")
    character = data.get("active_character")
    if character:
        parts.append(f"Character: {character}")
    persona = data.get("active_persona")
    if persona:
        parts.append(f"Persona: {persona}")
    return " | ".join(parts)


def collect_session_context(
    *,
    settings: Optional[SettingsManager] = None,
    include_roots: bool = False,
) -> dict[str, Any]:
    """Collect lightweight SillyTavern session context for prompting."""
    snapshot: dict[str, Any] = {"ok": False}
    silly_summary: dict[str, Any] = {"ok": False, "available": False}
    snapshot["sillytavern"] = silly_summary

    if SillyTavernBridge is None:  # pragma: no cover - optional dependency
        silly_summary["error"] = "SillyTavern bridge unavailable"
        return snapshot

    try:
        bridge = SillyTavernBridge(settings=settings)
    except Exception as exc:  # pragma: no cover - defensive
        silly_summary["error"] = str(exc)
        return snapshot

    try:
        payload = bridge.get_active()
    except SillyTavernBridgeError as exc:
        silly_summary["error"] = str(exc)
        return snapshot
    except Exception as exc:  # pragma: no cover - defensive
        silly_summary["error"] = str(exc)
        return snapshot
    finally:
        try:
            bridge.close()
        except Exception:  # pragma: no cover - defensive
            pass

    silly_summary["available"] = True
    if not isinstance(payload, Mapping):
        silly_summary["error"] = "invalid response"
        return snapshot

    silly_summary["ok"] = True
    silly_summary["raw"] = dict(payload)
    silly_summary["active_world"] = payload.get("activeWorld") or payload.get(
        "active_world"
    )
    silly_summary["active_character"] = payload.get("activeCharacter") or payload.get(
        "active_character"
    )
    silly_summary["active_persona"] = payload.get("activePersona") or payload.get(
        "active_persona"
    )
    silly_summary["timestamp"] = payload.get("timestamp")
    if include_roots:
        silly_summary["roots"] = payload.get("roots")
    silly_summary["summary"] = _summarise_active_context(silly_summary)
    snapshot["ok"] = True
    return snapshot


__all__ = [
    "SessionContext",
    "SessionSyncResult",
    "SessionSyncError",
    "build_session_context",
    "collect_session_context",
    "load_scene_dialogue",
    "normalise_messages",
    "sync_session",
]
