from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence


@dataclass(slots=True)
class GoldenDiffMismatch:
    path: str
    expected: Any
    actual: Any
    message: str


@dataclass(slots=True)
class GoldenDiffResult:
    ok: bool
    mismatches: Sequence[GoldenDiffMismatch]

    def raise_for_diff(self) -> None:
        if self.ok:
            return
        details = "\\n".join(
            f"- {m.message} @ {m.path} (expected={m.expected!r}, actual={m.actual!r})"
            for m in self.mismatches
        )
        raise AssertionError(f"golden diff failed:\\n{details}")


def load_trace(path: str | Path) -> Mapping[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_traces(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    ignore_paths: Iterable[str] | None = None,
) -> GoldenDiffResult:
    mismatches = diff_traces(expected, actual, ignore_paths=ignore_paths)
    return GoldenDiffResult(ok=not mismatches, mismatches=mismatches)


def compare_trace_files(
    expected_path: str | Path,
    actual_path: str | Path,
    *,
    ignore_paths: Iterable[str] | None = None,
) -> GoldenDiffResult:
    """Load two trace files and compare their canonical contents."""

    expected = load_trace(expected_path)
    actual = load_trace(actual_path)
    return compare_traces(expected, actual, ignore_paths=ignore_paths)


def _parse_step_path(path: str) -> tuple[Optional[int], Optional[str]]:
    if not path.startswith("steps["):
        return None, None
    closing = path.find("]")
    if closing == -1:
        return None, None
    index_str = path[len("steps[") : closing]
    if not index_str.isdigit():
        return None, None
    remainder = path[closing + 1 :]
    if remainder.startswith("."):
        remainder = remainder[1:]
    return int(index_str), remainder or None


def _parse_choice_path(remainder: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    if not remainder or not remainder.startswith("available_choices["):
        return None, remainder
    closing = remainder.find("]")
    if closing == -1:
        return None, remainder
    index_str = remainder[len("available_choices[") : closing]
    if not index_str.isdigit():
        return None, remainder
    rest = remainder[closing + 1 :]
    if rest.startswith("."):
        rest = rest[1:]
    return int(index_str), rest or None


def _extract_step_index(entry: Mapping[str, Any]) -> Optional[int]:
    value = entry.get("index")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.isdigit():
            return int(candidate)
    return None


def _map_steps_by_index(entries: Sequence[Any]) -> dict[int, Mapping[str, Any]]:
    indexed: dict[int, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            return {}
        idx = _extract_step_index(entry)
        if idx is None:
            return {}
        indexed[idx] = entry
    return indexed


def _format_step_message(step_index: int, remainder: Optional[str], base: str) -> str:
    if not remainder:
        if base == "missing key":
            return f"step {step_index} missing entry"
        if base == "unexpected key":
            return f"step {step_index} unexpected entry"
        if base == "length mismatch":
            return f"step {step_index} entry count mismatch"
        return f"step {step_index} {base}"

    choice_index, choice_remainder = _parse_choice_path(remainder)
    if choice_index is not None:
        if not choice_remainder:
            if base == "missing key":
                return f"step {step_index} choice[{choice_index}] missing"
            if base == "unexpected key":
                return f"step {step_index} choice[{choice_index}] unexpected"
            if base == "length mismatch":
                return f"step {step_index} available choice count changed"
            return f"step {step_index} choice[{choice_index}] {base}"
        readable = choice_remainder.replace("_", " ")
        if choice_remainder == "id" and base == "value mismatch":
            return f"step {step_index} choice[{choice_index}] id changed"
        if choice_remainder == "target" and base == "value mismatch":
            return f"step {step_index} choice[{choice_index}] target changed"
        if choice_remainder == "text" and base == "value mismatch":
            return f"step {step_index} choice[{choice_index}] text changed"
        return f"step {step_index} choice[{choice_index}] {readable} {base}"

    token = remainder
    if token == "to_node":
        return f"step {step_index} transitions to different node"
    if token == "from_node":
        return f"step {step_index} origin node changed"
    if token == "choice_id":
        return f"step {step_index} choice id changed"
    if token == "choice_target":
        return f"step {step_index} choice target changed"
    if token == "choice_text":
        return f"step {step_index} choice text changed"
    if token == "variables_digest":
        return f"step {step_index} variables digest changed"
    if token == "history_length":
        return f"step {step_index} history length changed"
    if token == "finished":
        return f"step {step_index} finished flag changed"
    if token == "pov":
        return f"step {step_index} POV changed"
    if token == "index":
        return f"step {step_index} index changed (order drift)"
    if token == "assets":
        return f"step {step_index} asset references changed"
    if token == "available_choices":
        if base == "length mismatch":
            return f"step {step_index} available choice count changed"
        return f"step {step_index} available choices {base}"
    if token.startswith("rng_before") or token.startswith("rng_after"):
        phase = "before" if token.startswith("rng_before") else "after"
        sub_field = token.split(".", 1)[1] if "." in token else ""
        if sub_field:
            return f"step {step_index} RNG {phase} {sub_field} changed"
        return f"step {step_index} RNG {phase} changed"
    if token.startswith("available_choices"):
        return f"step {step_index} available choices detail {base}"
    if token.startswith("variables"):
        return f"step {step_index} variables {base}"
    if token.startswith("history"):
        return f"step {step_index} history {base}"
    return f"step {step_index} {token.replace('_', ' ')} {base}"


def _format_message(path: str, base: str) -> str:
    step_index, remainder = _parse_step_path(path)
    if step_index is not None:
        return _format_step_message(step_index, remainder, base)
    if path == "steps":
        if base == "length mismatch":
            return "step count changed"
        return f"steps {base}"
    if path.startswith("meta."):
        field = path.split(".", 1)[1]
        if field == "worldline":
            return "trace worldline changed"
        if field == "pov":
            return "trace POV changed"
        if field == "workflow":
            return "workflow label changed"
        if field == "seed":
            return "seed changed"
        if field == "prompt_packs":
            return "prompt pack metadata changed"
        if field == "steps_recorded":
            return "recorded step count changed"
        return f"meta.{field} {base}"
    if path.startswith("config."):
        field = path.split(".", 1)[1]
        if field == "worldline":
            return "config worldline changed"
        if field == "variables":
            return "config variables changed"
        if field == "metadata":
            return "config metadata changed"
        return f"config.{field} {base}"
    if path.startswith("provenance."):
        field = path.split(".", 1)[1]
        if field == "worldline":
            return "provenance worldline changed"
        if field == "asset_manifest":
            return "provenance asset manifest changed"
        if field == "digest":
            return "digest changed"
        return f"provenance.{field} {base}"
    if path.startswith("assets."):
        field = path.split(".", 1)[1]
        if base == "length mismatch":
            return f"asset manifest '{field}' count changed"
        return f"asset manifest '{field}' entries changed"
    if path.startswith("initial.assets"):
        return "initial asset snapshot changed"
    if path.startswith("final.assets"):
        return "final asset snapshot changed"
    if path.startswith("initial.worldline"):
        return "initial worldline metadata changed"
    if path.startswith("final.worldline"):
        return "final worldline metadata changed"
    return f"{path} {base}"


def _child_path(parent: str, token: Any) -> str:
    if parent == "<root>":
        return str(token)
    return f"{parent}.{token}"


def _should_ignore(path: str, ignore: set[str]) -> bool:
    if path in ignore:
        return True
    return any(
        path.startswith(prefix.rstrip("*")) for prefix in ignore if prefix.endswith("*")
    )


def diff_traces(
    expected: Any,
    actual: Any,
    *,
    path: str = "<root>",
    ignore_paths: Iterable[str] | None = None,
) -> List[GoldenDiffMismatch]:
    ignore = set(ignore_paths or ())
    if _should_ignore(path, ignore):
        return []
    if type(expected) is not type(actual):
        return [
            GoldenDiffMismatch(
                path=path,
                expected=type(expected).__name__,
                actual=type(actual).__name__,
                message=_format_message(path, "type mismatch"),
            )
        ]
    if isinstance(expected, Mapping):
        errors: List[GoldenDiffMismatch] = []
        exp_keys = set(expected.keys())
        act_keys = set(actual.keys())
        for missing in sorted(exp_keys - act_keys):
            key_path = _child_path(path, missing)
            if _should_ignore(key_path, ignore):
                continue
            errors.append(
                GoldenDiffMismatch(
                    path=key_path,
                    expected=expected[missing],
                    actual=None,
                    message=_format_message(key_path, "missing key"),
                )
            )
        for extra in sorted(act_keys - exp_keys):
            key_path = _child_path(path, extra)
            if _should_ignore(key_path, ignore):
                continue
            errors.append(
                GoldenDiffMismatch(
                    path=key_path,
                    expected=None,
                    actual=actual[extra],
                    message=_format_message(key_path, "unexpected key"),
                )
            )
        for key in sorted(exp_keys & act_keys):
            key_path = _child_path(path, key)
            errors.extend(
                diff_traces(
                    expected[key],
                    actual[key],
                    path=key_path,
                    ignore_paths=ignore,
                )
            )
        return errors
    if isinstance(expected, list):
        errors: List[GoldenDiffMismatch] = []
        if len(expected) != len(actual):
            errors.append(
                GoldenDiffMismatch(
                    path=path,
                    expected=len(expected),
                    actual=len(actual),
                    message=_format_message(path, "length mismatch"),
                )
            )
        expected_map = _map_steps_by_index(expected)
        actual_map = _map_steps_by_index(actual)
        if expected_map and actual_map:
            for missing_idx in sorted(expected_map.keys() - actual_map.keys()):
                entry_path = f"{path}[{missing_idx}]"
                if _should_ignore(entry_path, ignore):
                    continue
                errors.append(
                    GoldenDiffMismatch(
                        path=entry_path,
                        expected=expected_map[missing_idx],
                        actual=None,
                        message=_format_message(entry_path, "missing key"),
                    )
                )
            for extra_idx in sorted(actual_map.keys() - expected_map.keys()):
                entry_path = f"{path}[{extra_idx}]"
                if _should_ignore(entry_path, ignore):
                    continue
                errors.append(
                    GoldenDiffMismatch(
                        path=entry_path,
                        expected=None,
                        actual=actual_map[extra_idx],
                        message=_format_message(entry_path, "unexpected key"),
                    )
                )
            for idx in sorted(expected_map.keys() & actual_map.keys()):
                entry_path = f"{path}[{idx}]"
                errors.extend(
                    diff_traces(
                        expected_map[idx],
                        actual_map[idx],
                        path=entry_path,
                        ignore_paths=ignore,
                    )
                )
            return errors
        for idx, (exp_item, act_item) in enumerate(zip(expected, actual)):
            item_path = f"{path}[{idx}]"
            errors.extend(
                diff_traces(
                    exp_item,
                    act_item,
                    path=item_path,
                    ignore_paths=ignore,
                )
            )
        return errors
    if expected != actual:
        return [
            GoldenDiffMismatch(
                path=path,
                expected=expected,
                actual=actual,
                message=_format_message(path, "value mismatch"),
            )
        ]
    return []
