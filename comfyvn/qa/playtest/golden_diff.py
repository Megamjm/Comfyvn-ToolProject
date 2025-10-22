from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Sequence


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
        if not self.ok:
            details = "\n".join(
                f"{m.path}: {m.message} (expected={m.expected!r}, actual={m.actual!r})"
                for m in self.mismatches
            )
            raise AssertionError(f"golden diff failed:\n{details}")


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
                message="type mismatch",
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
                    message="missing key",
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
                    message="unexpected key",
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
                    message="length mismatch",
                )
            )
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
                message="value mismatch",
            )
        ]
    return []


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
