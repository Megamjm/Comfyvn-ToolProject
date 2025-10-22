from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence

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
        }
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
        _dispatch_scene_events(runner, state, initial_peek, timestamp=0.0)

        start_payload = {
            "scene_id": runner.scene_id,
            "seed": seed_value,
            "pov": pov_value,
            "prompt_packs": prompt_pack_list,
            "workflow": workflow or "default",
            "variables_digest": _variables_digest(state.get("variables", {})),
            "persist": persist_trace,
            "timestamp": time.time(),
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
                "timestamp": time.time(),
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

        final_state = {
            "state": _canonicalize(state),
            "history": _canonicalize(state.get("history", [])),
            "finished": bool(state.get("finished")),
            "variables_digest": _variables_digest(state.get("variables", {})),
            "rng": dict(_snapshot_rng(state)),
        }

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
            },
            "config": {
                "seed": seed_value,
                "pov": pov_value,
                "variables": _canonicalize(variables or {}),
                "prompt_packs": prompt_pack_list,
                "workflow": workflow or "default",
                "metadata": _canonicalize(metadata or {}),
                "persist": persist_trace,
                "dry_run": not persist_trace,
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
            },
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
            "timestamp": time.time(),
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
            }
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
            "Playtest run completed (scene=%s seed=%s pov=%s steps=%s digest=%s persisted=%s path=%s log=%s)",
            runner.scene_id,
            seed_value,
            pov_value,
            len(steps),
            digest[:12],
            run.persisted,
            str(run.trace_path) if run.trace_path else "",
            str(run.log_path) if run.log_path else "",
        )
        return run
