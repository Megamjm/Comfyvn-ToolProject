from __future__ import annotations

import copy
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import comfyvn
from comfyvn.config.runtime_paths import logs_dir
from comfyvn.core import modder_hooks
from comfyvn.runner import ScenarioRunner, ValidationError

LOGGER = logging.getLogger("comfyvn.qa.playtest")

TRACE_SCHEMA_VERSION = "1.0"
RUNNER_VERSION = "2025.11"
DEFAULT_MAX_STEPS = 256


class PlaytestError(RuntimeError):
    """Domain-specific wrapper around scenario validation/runtime failures."""

    def __init__(
        self, message: str, *, issues: Optional[Sequence[Mapping[str, Any]]] = None
    ) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


@dataclass(slots=True)
class PlaytestStep:
    """Represents a deterministic transition between two scenario nodes."""

    index: int
    from_node: str
    to_node: str
    choice_id: Optional[str]
    choice_target: Optional[str]
    choice_text: Optional[str]
    rng_before: Mapping[str, Any]
    rng_after: Mapping[str, Any]
    variables: Mapping[str, Any]
    variables_digest: str
    history_length: int
    finished: bool
    pov: str
    available_choices: Sequence[Mapping[str, Any]]
    assets: Mapping[str, Sequence[str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "choice_id": self.choice_id,
            "choice_target": self.choice_target,
            "choice_text": self.choice_text,
            "rng_before": dict(self.rng_before),
            "rng_after": dict(self.rng_after),
            "variables": _canonicalize(self.variables),
            "variables_digest": self.variables_digest,
            "history_length": self.history_length,
            "finished": self.finished,
            "pov": self.pov,
            "available_choices": [
                _canonicalize(choice) for choice in self.available_choices
            ],
            "assets": _canonicalize(self.assets),
        }


@dataclass(slots=True)
class PlaytestRun:
    """Container for a completed playtest trace."""

    trace: Mapping[str, Any]
    digest: str
    scene_id: str
    seed: int
    pov: str
    trace_path: Optional[Path] = None
    persisted: bool = False
    log_path: Optional[Path] = None
    worldline: Optional[str] = None
    asset_manifest: Mapping[str, Sequence[str]] | None = None

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.trace, indent=indent, sort_keys=True)

    @property
    def digest_prefix(self) -> str:
        return self.digest[:12]

    def write(self, directory: Optional[Path] = None, *, indent: int = 2) -> Path:
        if directory is not None:
            target_dir = Path(directory)
        elif self.trace_path is not None:
            target_dir = Path(self.trace_path).parent
        else:
            target_dir = logs_dir("playtest")
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.scene_id}.{self.seed}.{self.digest_prefix}.trace.json"
        path = target_dir / filename
        path.write_text(self.to_json(indent=indent), encoding="utf-8")
        self.trace_path = path
        self.persisted = True
        log_entry = {
            "scene_id": self.scene_id,
            "seed": self.seed,
            "pov": self.pov,
            "steps": len(self.trace.get("steps", [])),
            "digest": self.digest,
            "persisted": True,
            "worldline": self.worldline,
        }
        if self.asset_manifest:
            log_entry["asset_manifest"] = _canonicalize(self.asset_manifest)
        log_path = target_dir / f"{self.scene_id}.{self.seed}.{self.digest_prefix}.log"
        log_path.write_text(
            json.dumps(log_entry, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.log_path = log_path
        return path


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda item: str(item[0]))
        return {k: _canonicalize(v) for k, v in items}
    if isinstance(value, list | tuple):
        return [_canonicalize(v) for v in value]
    return value


def _variables_digest(payload: Mapping[str, Any]) -> str:
    canonical = _canonicalize(payload)
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _snapshot_rng(state: Mapping[str, Any]) -> Mapping[str, Any]:
    rng_state = state.get("rng")
    if isinstance(rng_state, Mapping):
        return {
            "seed": int(rng_state.get("seed", 0)),
            "value": int(rng_state.get("value", 0)),
            "uses": int(rng_state.get("uses", 0)),
        }
    return {"seed": 0, "value": 0, "uses": 0}


def _dispatch_scene_events(
    runner: ScenarioRunner,
    state: Mapping[str, Any],
    peek: Mapping[str, Any],
    *,
    timestamp: float,
) -> None:
    node_payload = peek.get("node") or {}
    node_id = str(node_payload.get("id") or state.get("current_node"))
    scene_payload = {
        "scene_id": runner.scene_id,
        "node": node_id,
        "pov": state.get("pov"),
        "variables": state.get("variables"),
        "history": state.get("history"),
        "finished": bool(state.get("finished")),
        "timestamp": timestamp,
    }
    choices_payload = {
        "scene_id": runner.scene_id,
        "node": node_id,
        "choices": peek.get("choices") or [],
        "pov": state.get("pov"),
        "finished": bool(peek.get("finished")),
        "timestamp": timestamp,
    }
    try:
        modder_hooks.emit("on_scene_enter", scene_payload)
        modder_hooks.emit("on_choice_render", choices_payload)
    except Exception:
        LOGGER.debug("Modder hooks dispatch failed during playtest run", exc_info=True)


def _match_choice(
    choices: Sequence[Mapping[str, Any]], marker: Optional[str]
) -> tuple[Optional[Mapping[str, Any]], Optional[str]]:
    if marker is None:
        return None, None
    for choice in choices:
        candidate = choice.get("id") or choice.get("target")
        if candidate == marker:
            return choice, candidate
    return None, marker


_ASSET_KEY_KIND: Mapping[str, str] = {
    "asset": "assets",
    "asset_id": "assets",
    "asset_uid": "assets",
    "assets": "assets",
    "background": "backgrounds",
    "backgrounds": "backgrounds",
    "bg": "backgrounds",
    "bgm": "music",
    "music": "music",
    "sound": "sfx",
    "sfx": "sfx",
    "voice": "voices",
    "voices": "voices",
    "sprite": "sprites",
    "sprites": "sprites",
    "character": "characters",
    "characters": "characters",
    "layer": "layers",
    "layers": "layers",
    "prop": "props",
    "props": "props",
    "prompt": "prompts",
    "prompts": "prompts",
    "effect": "effects",
    "effects": "effects",
    "animation": "animations",
    "animations": "animations",
    "timeline": "timelines",
    "timelines": "timelines",
    "cg": "cgs",
    "cgs": "cgs",
    "video": "videos",
    "videos": "videos",
}

_ASSET_LOOKUP_KEYS = (
    "id",
    "uid",
    "slug",
    "name",
    "path",
    "file",
    "asset",
    "ref",
    "target",
    "value",
    "uri",
)

_COLLECTION_HINT_KEYS = (
    "items",
    "entries",
    "assets",
    "layers",
    "sprites",
    "tracks",
    "choices",
    "children",
    "nodes",
    "clips",
    "props",
)


def _asset_kind_from_key(raw_key: str) -> Optional[str]:
    key = raw_key.lower()
    if key in _ASSET_KEY_KIND:
        return _ASSET_KEY_KIND[key]
    if key.endswith("_asset") or key.endswith("_assets"):
        return "assets"
    if key.endswith("_background") or key.endswith("_backgrounds"):
        return "backgrounds"
    if key.endswith("_bgm") or key.endswith("_music"):
        return "music"
    if key.endswith("_sfx") or key.endswith("_sound"):
        return "sfx"
    if key.endswith("_voice") or key.endswith("_voices"):
        return "voices"
    if key.endswith("_sprite") or key.endswith("_sprites"):
        return "sprites"
    if key.endswith("_character") or key.endswith("_characters"):
        return "characters"
    if key.endswith("_layer") or key.endswith("_layers"):
        return "layers"
    if key.endswith("_prop") or key.endswith("_props"):
        return "props"
    if key.endswith("_prompt") or key.endswith("_prompts"):
        return "prompts"
    if key.endswith("_effect") or key.endswith("_effects"):
        return "effects"
    if key.endswith("_animation") or key.endswith("_animations"):
        return "animations"
    if key.endswith("_timeline") or key.endswith("_timelines"):
        return "timelines"
    if key.endswith("_video") or key.endswith("_videos"):
        return "videos"
    if key.endswith("_cg") or key.endswith("_cgs"):
        return "cgs"
    return None


def _collect_asset_values(value: Any) -> list[str]:
    results: list[str] = []

    def _push(raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                results.append(candidate)
        elif isinstance(raw, (int, float)):
            results.append(str(raw))

    def _walk(obj: Any, depth: int = 0) -> None:
        if obj is None:
            return
        if isinstance(obj, (str, int, float)):
            _push(obj)
            return
        if isinstance(obj, Mapping):
            for key in _ASSET_LOOKUP_KEYS:
                if key in obj:
                    _push(obj[key])
            for sub_key, sub_value in obj.items():
                lowered = str(sub_key).lower()
                if lowered in _ASSET_KEY_KIND or lowered.endswith("_id"):
                    _walk(sub_value, depth + 1)
                elif lowered in _COLLECTION_HINT_KEYS:
                    _walk(sub_value, depth + 1)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item, depth + 1)

    _walk(value)
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in results:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _extract_assets(node: Mapping[str, Any] | None) -> Mapping[str, Sequence[str]]:
    if not isinstance(node, Mapping):
        return {}

    collected: dict[str, set[str]] = {}

    def _record(kind: str, refs: Iterable[str]) -> None:
        if not refs:
            return
        bucket = collected.setdefault(kind, set())
        for ref in refs:
            ref_str = str(ref).strip()
            if ref_str:
                bucket.add(ref_str)

    for key, value in node.items():
        kind = _asset_kind_from_key(str(key).lower())
        if kind:
            _record(kind, _collect_asset_values(value))

    for field in ("actions", "choices", "metadata", "sidecar", "assets", "payload"):
        payload = node.get(field)
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                kind = _asset_kind_from_key(str(key).lower())
                if kind:
                    _record(kind, _collect_asset_values(value))
        elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            for entry in payload:
                if isinstance(entry, Mapping):
                    for key, value in entry.items():
                        kind = _asset_kind_from_key(str(key).lower())
                        if kind:
                            _record(kind, _collect_asset_values(value))
    return {kind: sorted(values) for kind, values in collected.items()}


def _merge_asset_index(
    index: MutableMapping[str, set[str]],
    snapshot: Mapping[str, Sequence[str]],
) -> None:
    for kind, values in snapshot.items():
        if not values:
            continue
        bucket = index.setdefault(kind, set())
        for value in values:
            normalized = str(value).strip()
            if normalized:
                bucket.add(normalized)


def _normalize_worldline(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Mapping):
        for key in ("worldline", "id", "uid", "slug", "name"):
            candidate = value.get(key)
            normalized = _normalize_worldline(candidate)
            if normalized:
                return normalized
        return None
    return _normalize_worldline(str(value))


def _resolve_worldline(
    explicit: Any,
    metadata: Optional[Mapping[str, Any]],
    scene: Mapping[str, Any],
    state: Mapping[str, Any],
) -> Optional[str]:
    scene_meta = scene.get("metadata")
    variables = state.get("variables") if isinstance(state, Mapping) else None
    candidates = [
        explicit,
        metadata.get("worldline") if isinstance(metadata, Mapping) else None,
        scene.get("worldline"),
        scene_meta.get("worldline") if isinstance(scene_meta, Mapping) else None,
        state.get("worldline") if isinstance(state, Mapping) else None,
    ]
    if isinstance(variables, Mapping):
        candidates.append(variables.get("worldline"))
    for candidate in candidates:
        normalized = _normalize_worldline(candidate)
        if normalized:
            return normalized
    return None


def _slugify_token(value: str) -> str:
    if not value:
        return "default"
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or "default"


class HeadlessPlaytestRunner:
    """
    Deterministic headless harness around ``ScenarioRunner``.

    The runner collects a canonical JSON trace for downstream golden comparisons.
    """

    def __init__(self, *, log_dir: Optional[Path] = None) -> None:
        self._log_dir = Path(log_dir) if log_dir else logs_dir("playtest")
        self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def run(
        self,
        scene: Mapping[str, Any],
        *,
        seed: int = 0,
        variables: Optional[Mapping[str, Any]] = None,
        pov: Optional[str] = None,
        prompt_packs: Optional[Iterable[str]] = None,
        workflow: Optional[str] = None,
        max_steps: Optional[int] = None,
        persist: bool = True,
        metadata: Optional[Mapping[str, Any]] = None,
        worldline: Optional[str] = None,
    ) -> PlaytestRun:
        try:
            runner = ScenarioRunner(scene)
        except ValidationError as exc:
            raise PlaytestError("scene validation failed", issues=exc.issues) from exc
        except Exception as exc:
            raise PlaytestError(str(exc)) from exc

        seed_value = int(seed)
        pov_candidate = str(pov).strip() if isinstance(pov, str) else None
        prompt_pack_list = sorted({str(p).strip() for p in prompt_packs or () if p})
        max_allowed_steps = (
            int(max_steps) if max_steps is not None else DEFAULT_MAX_STEPS
        )
        persist_trace = bool(persist)
        metadata_payload = (
            copy.deepcopy(metadata) if isinstance(metadata, Mapping) else None
        )

        base_variables: Optional[MutableMapping[str, Any]] = None
        if variables:
            base_variables = copy.deepcopy(
                variables
            )  # ensure caller payload is untouched

        try:
            state = runner.initial_state(
                seed=seed_value, variables=base_variables, pov=pov_candidate
            )
        except Exception as exc:
            raise PlaytestError(f"failed to build initial state: {exc}") from exc

        pov_value = str(state.get("pov") or "")
        initial_peek = runner.peek(state)
        worldline_value = _resolve_worldline(worldline, metadata_payload, scene, state)
        asset_index: dict[str, set[str]] = {}
        initial_assets = _extract_assets(initial_peek.get("node"))
        _merge_asset_index(asset_index, initial_assets)
        _dispatch_scene_events(runner, state, initial_peek, timestamp=0.0)

        start_payload = {
            "scene_id": runner.scene_id,
            "seed": seed_value,
            "pov": pov_value,
            "prompt_packs": prompt_pack_list,
            "workflow": workflow or "default",
            "variables_digest": _variables_digest(state.get("variables", {})),
            "persist": persist_trace,
            "timestamp": 0.0,
            "worldline": worldline_value,
            "metadata": _canonicalize(metadata_payload or {}),
            "assets": initial_assets,
        }
        try:
            modder_hooks.emit("on_playtest_start", start_payload)
        except Exception:
            LOGGER.debug("Playtest start hook emission failed", exc_info=True)

        initial_snapshot = {
            "node": initial_peek.get("node"),
            "choices": [
                _canonicalize(choice) for choice in initial_peek.get("choices", [])
            ],
            "finished": bool(initial_peek.get("finished")),
            "variables": _canonicalize(state.get("variables", {})),
            "variables_digest": _variables_digest(state.get("variables", {})),
            "history": _canonicalize(state.get("history", [])),
            "rng": dict(_snapshot_rng(state)),
            "pov": state.get("pov"),
            "worldline": worldline_value,
            "assets": initial_assets,
        }

        steps: list[PlaytestStep] = []
        aborted = False
        previous_choices: Sequence[Mapping[str, Any]] = (
            initial_peek.get("choices") or []
        )

        for index in range(max_allowed_steps):
            if state.get("finished"):
                break

            history_before = list(state.get("history", []))
            rng_before = _snapshot_rng(state)

            try:
                next_state = runner.step(state, seed=seed_value, pov=pov_value)
            except Exception as exc:
                raise PlaytestError(
                    f"scenario step failed at index {index}: {exc}"
                ) from exc

            rng_after = _snapshot_rng(next_state)
            history_after = list(next_state.get("history", []))

            marker_entry = (
                history_after[-1] if len(history_after) > len(history_before) else None
            )
            marker = (
                marker_entry.get("choice")
                if isinstance(marker_entry, Mapping)
                else None
            )
            from_node = (
                marker_entry.get("node")
                if isinstance(marker_entry, Mapping) and marker_entry.get("node")
                else (
                    history_before[-1].get("node")
                    if history_before
                    else runner.start_node
                )
            )
            choice_payload, matched_marker = _match_choice(previous_choices, marker)

            peek_next = runner.peek(next_state)
            _dispatch_scene_events(
                runner, next_state, peek_next, timestamp=float(index + 1)
            )

            canonical_vars = _canonicalize(next_state.get("variables", {}))
            node_assets = _extract_assets(peek_next.get("node"))
            _merge_asset_index(asset_index, node_assets)
            step_entry = PlaytestStep(
                index=index,
                from_node=str(from_node),
                to_node=str(next_state.get("current_node")),
                choice_id=matched_marker,
                choice_target=(
                    str(choice_payload.get("target")) if choice_payload else None
                ),
                choice_text=str(choice_payload.get("text")) if choice_payload else None,
                rng_before=rng_before,
                rng_after=rng_after,
                variables=canonical_vars,
                variables_digest=_variables_digest(next_state.get("variables", {})),
                history_length=len(history_after),
                finished=bool(next_state.get("finished")),
                pov=str(next_state.get("pov") or ""),
                available_choices=peek_next.get("choices") or [],
                assets=node_assets,
            )
            steps.append(step_entry)

            playtest_step_payload = {
                "scene_id": runner.scene_id,
                "step_index": index,
                "from_node": step_entry.from_node,
                "to_node": step_entry.to_node,
                "choice_id": step_entry.choice_id,
                "choice_target": step_entry.choice_target,
                "choice_text": step_entry.choice_text,
                "variables_digest": step_entry.variables_digest,
                "rng_before": step_entry.rng_before,
                "rng_after": step_entry.rng_after,
                "finished": step_entry.finished,
                "timestamp": float(index + 1),
                "worldline": worldline_value,
                "assets": node_assets,
            }
            try:
                modder_hooks.emit("on_playtest_step", playtest_step_payload)
            except Exception:
                LOGGER.debug("Playtest step hook emission failed", exc_info=True)

            state = next_state
            previous_choices = peek_next.get("choices") or []

            if state.get("finished"):
                break
        else:
            aborted = True

        final_peek = runner.peek(state)
        final_assets = _extract_assets(final_peek.get("node"))
        _merge_asset_index(asset_index, final_assets)
        final_state = {
            "state": _canonicalize(state),
            "history": _canonicalize(state.get("history", [])),
            "finished": bool(state.get("finished")),
            "variables_digest": _variables_digest(state.get("variables", {})),
            "rng": dict(_snapshot_rng(state)),
            "worldline": worldline_value,
            "assets": final_assets,
            "available_choices": [
                _canonicalize(choice) for choice in final_peek.get("choices", [])
            ],
        }
        if final_peek.get("node") is not None:
            final_state["node"] = _canonicalize(final_peek.get("node"))

        asset_manifest = {kind: sorted(values) for kind, values in asset_index.items()}

        trace_body = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "meta": {
                "runner": "HeadlessPlaytestRunner",
                "runner_version": RUNNER_VERSION,
                "comfyvn_version": getattr(comfyvn, "__version__", "0.0.0"),
                "scene_id": runner.scene_id,
                "seed": seed_value,
                "pov": pov_value,
                "prompt_packs": prompt_pack_list,
                "workflow": workflow or "default",
                "max_steps": max_allowed_steps,
                "steps_recorded": len(steps),
                "aborted": aborted,
                "persisted": persist_trace,
                "worldline": worldline_value,
            },
            "config": {
                "seed": seed_value,
                "pov": pov_value,
                "variables": _canonicalize(variables or {}),
                "prompt_packs": prompt_pack_list,
                "workflow": workflow or "default",
                "metadata": _canonicalize(metadata_payload or {}),
                "persist": persist_trace,
                "dry_run": not persist_trace,
                "worldline": worldline_value,
            },
            "initial": initial_snapshot,
            "steps": [step.to_dict() for step in steps],
            "final": final_state,
            "provenance": {
                "tool": "HeadlessPlaytestRunner",
                "tool_version": RUNNER_VERSION,
                "comfyvn_version": getattr(comfyvn, "__version__", "0.0.0"),
                "seed": seed_value,
                "pov": pov_value,
                "workflow": workflow or "default",
                "prompt_packs": prompt_pack_list,
                "digest": None,
                "worldline": worldline_value,
                "asset_manifest": asset_manifest,
            },
            "assets": asset_manifest,
        }

        canonical_json = json.dumps(
            _canonicalize(trace_body),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(canonical_json).hexdigest()

        trace = dict(trace_body)
        trace["digest"] = digest
        trace["provenance"]["digest"] = digest

        summary_payload = {
            "scene_id": runner.scene_id,
            "seed": seed_value,
            "pov": pov_value,
            "digest": digest,
            "steps": len(steps),
            "aborted": aborted,
            "persisted": persist_trace,
            "timestamp": float(len(steps)),
            "worldline": worldline_value,
            "asset_manifest": asset_manifest,
        }
        try:
            modder_hooks.emit("on_playtest_finished", summary_payload)
        except Exception:
            LOGGER.debug("Playtest finished hook emission failed", exc_info=True)

        run = PlaytestRun(
            trace=trace,
            digest=digest,
            scene_id=runner.scene_id,
            seed=seed_value,
            pov=pov_value,
            persisted=persist_trace,
            worldline=worldline_value,
            asset_manifest=asset_manifest,
        )

        if persist_trace:
            filename = f"{runner.scene_id}.{seed_value}.{run.digest_prefix}.trace.json"
            path = self._log_dir / filename
            path.write_text(
                json.dumps(trace, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            run.trace_path = path
            run.persisted = True
            log_entry = {
                "scene_id": runner.scene_id,
                "seed": seed_value,
                "pov": pov_value,
                "steps": len(steps),
                "digest": digest,
                "persisted": True,
                "worldline": worldline_value,
            }
            if asset_manifest:
                log_entry["asset_manifest"] = asset_manifest
            log_path = (
                self._log_dir
                / f"{runner.scene_id}.{seed_value}.{run.digest_prefix}.log"
            )
            log_path.write_text(
                json.dumps(log_entry, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            run.log_path = log_path

        LOGGER.info(
            "Playtest run completed (scene=%s seed=%s pov=%s worldline=%s steps=%s digest=%s persisted=%s path=%s log=%s assets=%s)",
            runner.scene_id,
            seed_value,
            pov_value,
            worldline_value or "",
            len(steps),
            digest[:12],
            run.persisted,
            str(run.trace_path) if run.trace_path else "",
            str(run.log_path) if run.log_path else "",
            ",".join(sorted(asset_manifest.keys())) if asset_manifest else "",
        )
        return run

    def run_per_pov_suite(
        self,
        plan: Mapping[str, Mapping[str, Mapping[str, Any]]],
        *,
        seed_offset: int = 0,
        persist: bool = True,
        workflow: Optional[str] = None,
        golden_dir: Optional[str | Path] = None,
    ) -> Dict[str, Dict[str, PlaytestRun]]:
        """
        Execute a structured set of golden traces per POV.

        ``plan`` expects the shape ``{pov_id: {category: scene_payload}}`` where
        ``category`` can be ``linear``, ``choice``, ``battle`` (or additional
        buckets defined by the caller). ``scene_payload`` can either be the raw
        scene dictionary or a mapping containing a ``scene`` key plus optional
        overrides (``seed``, ``variables``, ``metadata``, ``worldline``,
        ``prompt_packs``, ``persist``, ``max_steps``). When ``golden_dir`` is
        provided, every successful run is persisted under
        ``<golden_dir>/<pov>/<category>/`` using the canonical trace naming
        scheme.
        """

        suite: Dict[str, Dict[str, PlaytestRun]] = {}
        golden_directory = Path(golden_dir) if golden_dir is not None else None
        for pov_id, categories in plan.items():
            pov_runs: Dict[str, PlaytestRun] = {}
            ordered_categories = list(categories.items())
            for index, (category, scene_entry) in enumerate(ordered_categories):
                if not isinstance(scene_entry, Mapping):
                    raise ValueError(
                        f"Golden suite entry for POV '{pov_id}' category '{category}' is not a mapping"
                    )

                overrides: dict[str, Any] = {}
                scene_payload: Mapping[str, Any] | None
                candidate_scene = scene_entry.get("scene")
                if isinstance(candidate_scene, Mapping) and candidate_scene.get(
                    "nodes"
                ):
                    scene_payload = candidate_scene
                    overrides = {
                        key: value
                        for key, value in scene_entry.items()
                        if key != "scene"
                    }
                else:
                    scene_payload = scene_entry
                    overrides = {}

                if not isinstance(scene_payload, Mapping):
                    raise ValueError(
                        f"Golden suite entry for POV '{pov_id}' category '{category}' must supply a scene mapping"
                    )

                config = dict(overrides)
                allowed_keys = {
                    "seed",
                    "variables",
                    "pov",
                    "prompt_packs",
                    "workflow",
                    "persist",
                    "metadata",
                    "worldline",
                    "max_steps",
                }
                unexpected = set(config) - allowed_keys
                if unexpected:
                    raise ValueError(
                        f"Golden suite entry for POV '{pov_id}' category '{category}' has unsupported overrides: {sorted(unexpected)}"
                    )

                seed_for_run = int(config.pop("seed", seed_offset + index))

                variables_override = config.pop("variables", None)
                if variables_override is not None and not isinstance(
                    variables_override, Mapping
                ):
                    raise ValueError(
                        f"Golden suite entry for POV '{pov_id}' category '{category}' expects 'variables' to be a mapping"
                    )

                pov_override_raw = config.pop("pov", None)
                if isinstance(pov_override_raw, str):
                    stripped = pov_override_raw.strip()
                    pov_for_run = stripped or None
                else:
                    pov_for_run = None
                if pov_for_run is None:
                    pov_for_run = (
                        None
                        if str(pov_id).strip() in {"", "auto", "default"}
                        else str(pov_id)
                    )

                prompt_packs_override = config.pop("prompt_packs", None)
                workflow_for_run = config.pop("workflow", workflow)
                persist_override = bool(config.pop("persist", persist))

                metadata_override_raw = config.pop("metadata", None)
                if metadata_override_raw is not None and not isinstance(
                    metadata_override_raw, Mapping
                ):
                    raise ValueError(
                        f"Golden suite entry for POV '{pov_id}' category '{category}' expects 'metadata' to be a mapping"
                    )

                worldline_override = config.pop("worldline", None)
                max_steps_override = config.pop("max_steps", None)
                if max_steps_override is not None:
                    max_steps_override = int(max_steps_override)

                if config:
                    # Defensive: should never trigger because we already removed all allowed keys.
                    raise ValueError(
                        f"Golden suite entry for POV '{pov_id}' category '{category}' produced residual overrides: {sorted(config)}"
                    )

                metadata_for_run: dict[str, Any] = {
                    "category": category,
                    "pov": pov_id,
                }
                if isinstance(metadata_override_raw, Mapping):
                    metadata_for_run.update(copy.deepcopy(metadata_override_raw))

                run = self.run(
                    scene_payload,
                    seed=seed_for_run,
                    variables=variables_override,
                    pov=pov_for_run,
                    prompt_packs=prompt_packs_override,
                    workflow=workflow_for_run,
                    persist=persist_override,
                    metadata=metadata_for_run,
                    max_steps=max_steps_override,
                    worldline=worldline_override,
                )

                if golden_directory is not None:
                    target_dir = (
                        golden_directory
                        / _slugify_token(str(pov_id))
                        / _slugify_token(str(category))
                    )
                    run.write(target_dir)

                pov_runs[category] = run
            suite[pov_id] = pov_runs
        return suite
