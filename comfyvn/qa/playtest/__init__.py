"""
Playtest harness helpers for deterministic scenario regression tests.

The module exposes two primary surfaces:

``headless_runner`` – deterministic orchestration around ``ScenarioRunner`` that
records JSON traces suitable for golden comparisons.

``golden_diff`` – lightweight diff helpers that validate headless runs against
checked-in golden files (used by CI and modders maintaining scripted suites).
"""

from __future__ import annotations

from .golden_diff import (
    GoldenDiffMismatch,
    GoldenDiffResult,
    compare_traces,
    diff_traces,
)
from .headless_runner import (
    HeadlessPlaytestRunner,
    PlaytestError,
    PlaytestRun,
    PlaytestStep,
)

__all__ = [
    "HeadlessPlaytestRunner",
    "PlaytestRun",
    "PlaytestStep",
    "PlaytestError",
    "GoldenDiffMismatch",
    "GoldenDiffResult",
    "compare_traces",
    "diff_traces",
]
