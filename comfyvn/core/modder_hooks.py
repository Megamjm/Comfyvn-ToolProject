from __future__ import annotations

"""
Central dispatch for modder-facing hook events.

The bus fans out events to:
  * synchronous listeners registered inside the process,
  * optional developer plugin modules (when dev mode is enabled),
  * asynchronous subscribers (used by REST/WS surfaces).

Hooks are described via ``HOOK_SPECS`` so the API and documentation can stay
in sync with the available payload fields.
"""

import asyncio
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

try:  # FastAPI server-side helper; optional for pure client usage.
    from comfyvn.server.core.plugins import PluginHost  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PluginHost = None  # type: ignore

LOGGER = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class HookSpec:
    name: str
    description: str
    payload_fields: Dict[str, str]
    ws_topic: str
    rest_event: str


HOOK_SPECS: Dict[str, HookSpec] = {
    "on_scene_enter": HookSpec(
        name="on_scene_enter",
        description="Fires when the scenario runner enters a node after a choice resolves.",
        payload_fields={
            "scene_id": "Scene identifier supplied in the payload.",
            "node": "Canonical node id that became active.",
            "pov": "Resolved POV identifier for the runner state.",
            "variables": "Deep copy of the runner variables after node actions.",
            "history": "Sequence of node/choice entries up to this point.",
            "finished": "Boolean flag when the scenario has no further choices.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_scene_enter",
        rest_event="on_scene_enter",
    ),
    "on_choice_render": HookSpec(
        name="on_choice_render",
        description="Published when the renderer computes visible choices for the active node.",
        payload_fields={
            "scene_id": "Scene identifier supplied in the payload.",
            "node": "Current node id used to generate choices.",
            "choices": "List of visible choice payloads (id, text, target, metadata).",
            "pov": "Resolved POV identifier for this render pass.",
            "finished": "Boolean flag indicating the runner has no remaining choices.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_choice_render",
        rest_event="on_choice_render",
    ),
    "on_asset_saved": HookSpec(
        name="on_asset_saved",
        description=(
            "Legacy alias for on_asset_registered; emitted alongside "
            "on_asset_registered for backward compatibility."
        ),
        payload_fields={
            "uid": "Asset registry uid derived from the file hash.",
            "type": "Asset registry type bucket (e.g. character.portrait).",
            "path": "Relative path under the assets root.",
            "meta": "Metadata payload persisted alongside the asset.",
            "sidecar": "Relative path to the generated sidecar JSON.",
            "bytes": "File size in bytes when available.",
            "hook_event": "Underlying AssetRegistry hook that produced the event.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_asset_saved",
        rest_event="on_asset_saved",
    ),
    "on_asset_registered": HookSpec(
        name="on_asset_registered",
        description="Fires after an asset is registered and its sidecar is written.",
        payload_fields={
            "uid": "Asset registry uid derived from the file hash.",
            "type": "Asset registry type bucket (e.g. character.portrait).",
            "path": "Relative path under the assets root.",
            "meta": "Metadata payload persisted alongside the asset.",
            "sidecar": "Relative path to the generated sidecar JSON.",
            "bytes": "File size in bytes when available.",
            "hook_event": "Underlying AssetRegistry hook that produced the event.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_asset_registered",
        rest_event="on_asset_registered",
    ),
    "on_asset_meta_updated": HookSpec(
        name="on_asset_meta_updated",
        description="Emitted when asset metadata or sidecar contents change.",
        payload_fields={
            "uid": "Asset registry uid derived from the file hash.",
            "type": "Asset registry type bucket when available.",
            "path": "Relative path under the assets root.",
            "meta": "Updated metadata payload persisted alongside the asset.",
            "sidecar": "Relative path to the regenerated sidecar JSON.",
            "hook_event": "Underlying AssetRegistry hook that produced the event.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_asset_meta_updated",
        rest_event="on_asset_meta_updated",
    ),
    "on_asset_removed": HookSpec(
        name="on_asset_removed",
        description="Broadcast after an asset registry row (and optional files) are removed.",
        payload_fields={
            "uid": "Removed asset uid.",
            "type": "Asset registry type bucket removed for context.",
            "path": "Relative path that previously referenced the asset.",
            "sidecar": "Relative path to the removed sidecar JSON.",
            "meta": "Metadata payload that was persisted for the asset prior to removal.",
            "bytes": "File size in bytes when previously registered (if known).",
            "hook_event": "Underlying AssetRegistry hook that produced the event.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_asset_removed",
        rest_event="on_asset_removed",
    ),
    "on_asset_sidecar_written": HookSpec(
        name="on_asset_sidecar_written",
        description="Emitted whenever an asset sidecar is written to disk.",
        payload_fields={
            "uid": "Asset registry uid derived from the file hash.",
            "type": "Asset registry type bucket when provided by the writer.",
            "sidecar": "Absolute path to the primary sidecar JSON.",
            "rel_path": "Asset-relative path whose sidecar was written.",
            "hook_event": "Underlying AssetRegistry hook that produced the event.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_asset_sidecar_written",
        rest_event="on_asset_sidecar_written",
    ),
    "on_rating_decision": HookSpec(
        name="on_rating_decision",
        description="Published whenever the rating service evaluates an item.",
        payload_fields={
            "item_id": "Identifier supplied to the classifier.",
            "rating": "Rating bucket selected (E/T/M/Adult).",
            "nsfw": "Boolean flag for NSFW buckets.",
            "confidence": "Classifier confidence score (0-1).",
            "mode": "Active filter mode (sfw|warn|unrestricted).",
            "source": "classifier|override depending on the decision.",
            "matched": "Keyword/tag matches that influenced the decision.",
            "ack_status": "Ack status when evaluated under SFW mode.",
        },
        ws_topic="modder.on_rating_decision",
        rest_event="on_rating_decision",
    ),
    "on_rating_override": HookSpec(
        name="on_rating_override",
        description="Emitted when a reviewer stores or removes a manual rating override.",
        payload_fields={
            "item_id": "Identifier whose rating changed.",
            "rating": "Rating bucket recorded by the override.",
            "reviewer": "Reviewer identifier recorded with the override.",
            "reason": "Reviewer provided justification.",
            "scope": "Scope string provided during override (asset|prompt|export).",
            "removed": "True when an override is cleared.",
            "timestamp": "Override timestamp (seconds).",
        },
        ws_topic="modder.on_rating_override",
        rest_event="on_rating_override",
    ),
    "on_rating_acknowledged": HookSpec(
        name="on_rating_acknowledged",
        description="Emitted when an acknowledgement token is confirmed.",
        payload_fields={
            "token": "Acknowledgement token string.",
            "item_id": "Identifier tied to the token.",
            "action": "Action scope passed to the evaluator.",
            "rating": "Rating bucket that triggered the ack.",
            "user": "User recorded in the acknowledgement entry.",
            "acknowledged_at": "Timestamp when the ack was confirmed.",
        },
        ws_topic="modder.on_rating_acknowledged",
        rest_event="on_rating_acknowledged",
    ),
    "on_worldline_diff": HookSpec(
        name="on_worldline_diff",
        description="Emitted after the diffmerge API computes node deltas between worldlines.",
        payload_fields={
            "source": "Source worldline identifier.",
            "target": "Target worldline identifier.",
            "mask_pov": "Boolean flag noting whether POV masking was applied.",
            "node_changes": "Node diff payload (added/removed/shared/changed).",
            "choice_changes": "Choice diff payload (added/removed/changed).",
            "timestamp": "UTC timestamp when the diff was computed.",
        },
        ws_topic="modder.on_worldline_diff",
        rest_event="on_worldline_diff",
    ),
    "on_worldline_merge": HookSpec(
        name="on_worldline_merge",
        description="Published when a worldline merge preview or apply is invoked.",
        payload_fields={
            "source": "Source worldline identifier.",
            "target": "Target worldline identifier.",
            "apply": "Boolean indicating whether the merge was applied.",
            "fast_forward": "Fast-forward flag from the merge attempt.",
            "added_nodes": "Nodes contributed by the source during a successful merge.",
            "conflicts": "Conflict payload when the merge aborted.",
            "timestamp": "UTC timestamp when the merge was evaluated.",
        },
        ws_topic="modder.on_worldline_merge",
        rest_event="on_worldline_merge",
    ),
    "on_cloud_sync_plan": HookSpec(
        name="on_cloud_sync_plan",
        description="Fires when a cloud sync dry-run computes a delta plan.",
        payload_fields={
            "service": "Provider identifier (e.g. s3, gdrive).",
            "snapshot": "Manifest snapshot label derived from the request.",
            "uploads": "Number of files scheduled for upload.",
            "deletes": "Number of remote files scheduled for deletion.",
            "bytes": "Total bytes planned for upload based on the manifest delta.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_cloud_sync_plan",
        rest_event="on_cloud_sync_plan",
    ),
    "on_cloud_sync_complete": HookSpec(
        name="on_cloud_sync_complete",
        description="Emitted after a cloud sync run completes successfully.",
        payload_fields={
            "service": "Provider identifier (e.g. s3, gdrive).",
            "snapshot": "Manifest snapshot label derived from the request.",
            "uploads": "Number of files uploaded during the run.",
            "deletes": "Number of files deleted remotely during the run.",
            "skipped": "Number of files unchanged during the run.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_cloud_sync_complete",
        rest_event="on_cloud_sync_complete",
    ),
    "on_weather_plan": HookSpec(
        name="on_weather_plan",
        description="Emitted when the weather planner compiles a new presentation plan.",
        payload_fields={
            "state": "Canonicalised weather state (time_of_day/weather/ambience).",
            "summary": "Background & overlay summary for quick diffs.",
            "transition": "Crossfade duration/ease/exposure shift fields.",
            "particles": "Particle payload when weather presets define one.",
            "sfx": "Loop path, gain, and tags applied to the ambience layer.",
            "meta": "Hash/version/timestamp + warnings emitted during compilation.",
            "trigger": "Source that initiated the update (e.g. api.weather.state.post).",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_weather_plan",
        rest_event="on_weather_plan",
    ),
    "on_accessibility_settings": HookSpec(
        name="on_accessibility_settings",
        description="Broadcast whenever accessibility preferences change (font scale, filters, high contrast, subtitles flag).",
        payload_fields={
            "state": "Persisted accessibility settings (font_scale, color_filter, high_contrast, subtitles_enabled).",
            "timestamp": "Event emission timestamp (UTC seconds).",
            "source": "Originator string such as accessibility.manager or api.accessibility.state.post.",
        },
        ws_topic="modder.on_accessibility_settings",
        rest_event="on_accessibility_settings",
    ),
    "on_accessibility_subtitle": HookSpec(
        name="on_accessibility_subtitle",
        description="Published when the viewer subtitle overlay updates or clears.",
        payload_fields={
            "text": "Subtitle text rendered on the overlay.",
            "origin": "Optional speaker/source label displayed above the subtitle.",
            "expires_at": "Epoch timestamp (seconds) when the subtitle will auto-clear; null when persistent.",
            "enabled": "Whether subtitles are enabled in accessibility preferences.",
            "timestamp": "Event emission timestamp (UTC seconds).",
            "reason": "Trace string describing why the update occurred (e.g. accessibility.subtitle.push).",
        },
        ws_topic="modder.on_accessibility_subtitle",
        rest_event="on_accessibility_subtitle",
    ),
    "on_accessibility_input_map": HookSpec(
        name="on_accessibility_input_map",
        description="Broadcast whenever input bindings for accessibility/controller profiles are updated.",
        payload_fields={
            "action": "Action identifier whose binding changed.",
            "binding": "Binding payload containing primary/secondary/controller entries.",
            "timestamp": "Event emission timestamp (UTC seconds).",
            "event_id": "Unique identifier for the change event.",
        },
        ws_topic="modder.on_accessibility_input_map",
        rest_event="on_accessibility_input_map",
    ),
    "on_accessibility_input": HookSpec(
        name="on_accessibility_input",
        description="Published when a mapped input action triggers (keyboard or controller).",
        payload_fields={
            "action": "Action identifier triggered (e.g. viewer.advance).",
            "source": "Source of the trigger (viewer, api, controller).",
            "meta": "Optional metadata dictionary forwarded from the trigger caller.",
            "timestamp": "Event emission timestamp (UTC seconds).",
            "event_id": "Unique identifier for the input trigger.",
        },
        ws_topic="modder.on_accessibility_input",
        rest_event="on_accessibility_input",
    ),
    "on_perf_budget_state": HookSpec(
        name="on_perf_budget_state",
        description="Emitted when performance budgets evaluate queue state, job transitions, or lazy asset unloads.",
        payload_fields={
            "trigger": "Action that produced the update (e.g. job.registered, asset.evicted).",
            "payload": "Structured payload describing the transition (limits, job, assets, metrics).",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_perf_budget_state",
        rest_event="on_perf_budget_state",
    ),
    "on_perf_profiler_snapshot": HookSpec(
        name="on_perf_profiler_snapshot",
        description="Profiler marks, spans, and dashboard snapshots for observability tooling.",
        payload_fields={
            "trigger": "Profiler action (span.recorded, mark.emitted, snapshot.generated, reset).",
            "payload": "Payload describing the mark/span/dashboard contents.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_perf_profiler_snapshot",
        rest_event="on_perf_profiler_snapshot",
    ),
    "on_battle_simulated": HookSpec(
        name="on_battle_simulated",
        description="Fires when a battle simulation produces an outcome/log without committing the branch.",
        payload_fields={
            "scene_id": "Optional scene identifier supplied by the client.",
            "node_id": "Optional node identifier for the active battle choice.",
            "pov": "POV used during the narration preview.",
            "outcome": "Winner selected by the deterministic simulation.",
            "seed": "Seed used for the RNG (helps reproduce narration).",
            "weights": "Normalised weight map applied during the roll.",
            "log": "Narration log entries rendered during the simulation.",
            "persisted": "Whether the caller requested RNG state to persist.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_battle_simulated",
        rest_event="on_battle_simulated",
    ),
    "on_battle_resolved": HookSpec(
        name="on_battle_resolved",
        description="Emitted after a battle outcome is committed to the scenario variables.",
        payload_fields={
            "scene_id": "Optional scene identifier supplied by the client.",
            "node_id": "Optional node identifier for the resolved battle.",
            "pov": "POV active when the outcome was chosen.",
            "outcome": "Branch identifier applied to vars.battle_outcome.",
            "vars": "Variables payload returned to the caller.",
            "persisted": "Whether vars/state were persisted.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_battle_resolved",
        rest_event="on_battle_resolved",
    ),
    "on_playtest_start": HookSpec(
        name="on_playtest_start",
        description="Fires when the headless playtest harness begins executing a scene.",
        payload_fields={
            "scene_id": "Scene identifier derived from the payload.",
            "seed": "Seed supplied to the deterministic playtest runner.",
            "pov": "Resolved POV for the initial state.",
            "prompt_packs": "Prompt packs requested for the run (if any).",
            "workflow": "Workflow label carried through the regression trace.",
            "variables_digest": "SHA256 digest of the initial variables payload.",
            "persist": "Boolean flag indicating whether the trace will be persisted to disk.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_playtest_start",
        rest_event="on_playtest_start",
    ),
    "on_playtest_step": HookSpec(
        name="on_playtest_step",
        description="Published after each deterministic step recorded by the playtest harness.",
        payload_fields={
            "scene_id": "Scene identifier executed by the runner.",
            "step_index": "Zero-based index of the step within the trace.",
            "from_node": "Node identifier that emitted the choice.",
            "to_node": "Node identifier entered after applying the choice.",
            "choice_id": "Identifier of the resolved choice (id or target).",
            "choice_target": "Target node id recorded for the choice.",
            "choice_text": "Label associated with the choice when provided.",
            "variables_digest": "SHA256 digest of the variables after the step.",
            "rng_before": "Deterministic RNG state prior to evaluating the choice.",
            "rng_after": "Deterministic RNG state after evaluating the choice.",
            "finished": "Boolean flag indicating whether the scene finished after this step.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_playtest_step",
        rest_event="on_playtest_step",
    ),
    "on_playtest_finished": HookSpec(
        name="on_playtest_finished",
        description="Emitted when the headless playtest harness completes (or aborts) a run.",
        payload_fields={
            "scene_id": "Scene identifier executed by the runner.",
            "seed": "Seed supplied to the deterministic playtest runner.",
            "pov": "Resolved POV for the final state.",
            "digest": "SHA256 digest of the canonical trace payload.",
            "steps": "Number of steps recorded during the run.",
            "aborted": "Boolean flag when the harness hit a max-steps guard.",
            "persisted": "Boolean flag indicating whether the JSON trace was written to disk.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_playtest_finished",
        rest_event="on_playtest_finished",
    ),
    "on_export_publish_preview": HookSpec(
        name="on_export_publish_preview",
        description="Emitted when export.publish runs in dry-run mode and prepares package diffs.",
        payload_fields={
            "project_id": "Project identifier supplied to the export pipeline.",
            "timeline_id": "Timeline identifier resolved for the export.",
            "targets": "List of publish targets requested (steam, itch).",
            "label": "Human-readable label planned for the package.",
            "version": "Version string supplied in the request (if any).",
            "platforms": "Platforms that would be packaged for each target.",
            "diffs": "Planned diff summary describing new/modified artefacts.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_export_publish_preview",
        rest_event="on_export_publish_preview",
    ),
    "on_export_publish_complete": HookSpec(
        name="on_export_publish_complete",
        description="Emitted after export.publish writes a package archive to disk.",
        payload_fields={
            "project_id": "Project identifier supplied to the export pipeline.",
            "timeline_id": "Timeline identifier resolved for the export.",
            "target": "Publish target that completed (steam or itch).",
            "label": "Label applied to the package manifest.",
            "version": "Version string supplied in the request (if any).",
            "checksum": "SHA256 checksum of the archive.",
            "archive_path": "Absolute path to the generated archive.",
            "manifest_path": "Absolute path to the package manifest JSON.",
            "platforms": "Platforms included in the package.",
            "provenance": "Sidecar paths generated alongside the package.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_export_publish_complete",
        rest_event="on_export_publish_complete",
    ),
    "on_policy_enforced": HookSpec(
        name="on_policy_enforced",
        description="Published after the policy enforcer evaluates an action (import/export).",
        payload_fields={
            "action": "Action identifier supplied to the enforcer (e.g. export.bundle).",
            "allow": "Boolean flag indicating whether the action may proceed.",
            "counts": "Dictionary with total findings grouped by info|warn|block.",
            "blocked": "List of findings that produced a block outcome.",
            "warnings": "List of non-blocking findings.",
            "info": "List of informational findings retained for provenance.",
            "bundle": "Descriptor payload (project/timeline/metadata) supplied for the run.",
            "log_path": "Absolute path to the JSONL log storing the enforcement record.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_policy_enforced",
        rest_event="on_policy_enforced",
    ),
    "on_collab_operation": HookSpec(
        name="on_collab_operation",
        description="Emitted after collaborative CRDT operations mutate a scene document.",
        payload_fields={
            "scene_id": "Scene identifier whose document was updated.",
            "version": "Document version after applying the operations.",
            "clock": "Lamport clock recorded after processing.",
            "operations": "List of operations received (op_id, actor, kind, clock, payload).",
            "applied": "List of booleans mirroring operations to indicate which ones changed state.",
            "snapshot": "Document snapshot returned to the caller when the update broadcast included one.",
            "actor": "Client identifier that submitted the operations.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="modder.on_collab_operation",
        rest_event="on_collab_operation",
    ),
    "on_security_secret_read": HookSpec(
        name="on_security_secret_read",
        description="Emitted when the encrypted secrets store serves a provider payload.",
        payload_fields={
            "provider": "Provider identifier requested by the caller.",
            "keys": "List of secret field names returned (values omitted).",
            "overrides": "Environment override keys applied during resolution.",
            "present": "Boolean flag indicating whether the provider has stored secrets.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="security.secret_read",
        rest_event="on_security_secret_read",
    ),
    "on_security_key_rotated": HookSpec(
        name="on_security_key_rotated",
        description="Emitted after the secrets store re-encrypts data with a new key.",
        payload_fields={
            "fingerprint": "Leading SHA256 fingerprint for the active encryption key.",
            "providers": "Providers included in the re-encrypted payload.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="security.key_rotated",
        rest_event="on_security_key_rotated",
    ),
    "on_sandbox_network_blocked": HookSpec(
        name="on_sandbox_network_blocked",
        description="Published when the sandbox denies an outbound network connection.",
        payload_fields={
            "host": "Target host that was denied by the sandbox guard.",
            "port": "Port number requested by the caller.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="security.sandbox_blocked",
        rest_event="on_sandbox_network_blocked",
    ),
}

HookListener = Callable[[str, Dict[str, Any]], None]
Subscriber = Tuple[Optional[Set[str]], asyncio.Queue]


class ModderHookBus:
    """In-process fanout bus for modder hook events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: Dict[str, List[HookListener]] = {
            name: [] for name in HOOK_SPECS
        }
        self._subscribers: List[Subscriber] = []
        self._history: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._plugin_host = self._init_plugin_host()

    # ------------------------------------------------------------------ Helpers
    def _init_plugin_host(self):
        if PluginHost is None:
            return None
        dev_mode = _env_flag("COMFYVN_DEV_MODE")
        root_env = os.getenv("COMFYVN_MOD_PLUGIN_ROOT", "").strip()
        if root_env:
            root = Path(root_env)
        else:
            root = Path("dev/modder_hooks")
        if not dev_mode and not root.exists():
            return None
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception:  # pragma: no cover - defensive
            LOGGER.warning("Unable to create modder plugin directory %s", root)
            return None
        try:
            host = PluginHost(root=str(root))
            LOGGER.info(
                "ModderHookBus plugin host enabled (dev_mode=%s, root=%s)",
                dev_mode,
                root,
            )
            return host
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Modder plugin host unavailable: %s", exc)
            return None

    def _queue_put(self, queue: asyncio.Queue, data: Dict[str, Any]) -> None:
        try:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(data)
        except Exception:
            # Dropping delivery to a misbehaving subscriber should not impact others.
            pass

    def _notify_subscribers(self, event: str, envelope: Dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
            loop = self._loop
        if not subscribers:
            return
        if loop and loop.is_running():
            for topics, queue in subscribers:
                if topics and event not in topics:
                    continue
                loop.call_soon_threadsafe(self._queue_put, queue, envelope)
        else:
            for topics, queue in subscribers:
                if topics and event not in topics:
                    continue
                self._queue_put(queue, envelope)

    # ------------------------------------------------------------------ API
    def register_listener(
        self, listener: HookListener, events: Optional[Iterable[str]] = None
    ) -> None:
        if events is None:
            events = HOOK_SPECS.keys()
        with self._lock:
            for event in events:
                if event not in HOOK_SPECS:
                    raise ValueError(f"Unsupported modder hook: {event}")
                self._listeners[event].append(listener)

    def unregister_listener(
        self, listener: HookListener, events: Optional[Iterable[str]] = None
    ) -> None:
        with self._lock:
            targets = events or HOOK_SPECS.keys()
            for event in targets:
                if event not in self._listeners:
                    continue
                try:
                    self._listeners[event].remove(listener)
                except ValueError:
                    continue

    async def subscribe(self, topics: Optional[Sequence[str]] = None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        topic_filter: Optional[Set[str]] = None
        if topics:
            invalid = [t for t in topics if t not in HOOK_SPECS]
            if invalid:
                raise ValueError(
                    f"Unsupported modder hook topics: {', '.join(invalid)}"
                )
            topic_filter = set(topics)
        with self._lock:
            self._subscribers.append((topic_filter, queue))
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [
                entry for entry in self._subscribers if entry[1] is not queue
            ]
            if not self._subscribers:
                self._loop = None

    def emit(self, event: str, payload: Dict[str, Any]) -> None:
        if event not in HOOK_SPECS:
            LOGGER.debug("Dropping unsupported modder hook '%s'", event)
            return
        envelope = {
            "event": event,
            "ts": time.time(),
            "data": dict(payload),
        }
        with self._lock:
            self._history.append(envelope)
            listeners = list(self._listeners.get(event, ()))
        for listener in listeners:
            try:
                listener(event, payload)
            except Exception:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Modder hook listener failure for %s", event, exc_info=True
                )
        try:
            from comfyvn.obs.telemetry import get_telemetry

            get_telemetry().record_hook_event(event, payload)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Telemetry hook recording failed for %s", event, exc_info=True)
        if self._plugin_host:
            try:
                self._plugin_host.call(event, payload)
            except Exception:  # pragma: no cover - defensive
                LOGGER.warning("Modder plugin hook failed for %s", event, exc_info=True)
        self._notify_subscribers(event, envelope)

    def history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)[-min(max(limit, 1), len(self._history)) :]

    @property
    def plugin_host_enabled(self) -> bool:
        return self._plugin_host is not None

    def plugin_root(self) -> Optional[str]:
        if not self._plugin_host:
            return None
        return str(getattr(self._plugin_host, "root", "")) or None


_BUS = ModderHookBus()


def emit(event: str, payload: Dict[str, Any]) -> None:
    """Emit a modder hook event."""
    _BUS.emit(event, payload)


def hook_specs() -> Dict[str, HookSpec]:
    """Return the immutable hook specification mapping."""
    return dict(HOOK_SPECS)


def register_listener(
    listener: HookListener, events: Optional[Iterable[str]] = None
) -> None:
    _BUS.register_listener(listener, events)


def unregister_listener(
    listener: HookListener, events: Optional[Iterable[str]] = None
) -> None:
    _BUS.unregister_listener(listener, events)


async def subscribe(topics: Optional[Sequence[str]] = None) -> asyncio.Queue:
    return await _BUS.subscribe(topics)


def unsubscribe(queue: asyncio.Queue) -> None:
    _BUS.unsubscribe(queue)


def history(limit: int = 20) -> List[Dict[str, Any]]:
    return _BUS.history(limit)


def plugin_host_enabled() -> bool:
    return _BUS.plugin_host_enabled


def plugin_root() -> Optional[str]:
    return _BUS.plugin_root()
