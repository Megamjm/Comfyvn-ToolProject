from __future__ import annotations

import copy

from comfyvn.qa.playtest import HeadlessPlaytestRunner, compare_traces


def test_headless_runner_determinism(tmp_path, sample_playtest_scene):
    runner = HeadlessPlaytestRunner(log_dir=tmp_path)
    result_one = runner.run(sample_playtest_scene, seed=0, persist=False)
    result_two = runner.run(sample_playtest_scene, seed=0, persist=False)
    assert result_one.digest == result_two.digest
    assert result_one.trace["steps"] == result_two.trace["steps"]
    assert result_one.trace["final"]["finished"] is True


def test_headless_runner_seed_affects_trace(tmp_path, sample_playtest_scene):
    runner = HeadlessPlaytestRunner(log_dir=tmp_path)
    trace_a = runner.run(sample_playtest_scene, seed=3, persist=False)
    trace_b = runner.run(sample_playtest_scene, seed=682, persist=False)
    assert trace_a.digest != trace_b.digest
    assert trace_a.trace["steps"] != trace_b.trace["steps"]


def test_golden_diff_detects_changes(tmp_path, sample_playtest_scene):
    runner = HeadlessPlaytestRunner(log_dir=tmp_path)
    reference = runner.run(sample_playtest_scene, seed=5, persist=False)

    # Exact match passes
    result = compare_traces(reference.trace, copy.deepcopy(reference.trace))
    assert result.ok

    # Mutated trace triggers mismatch
    mutated = copy.deepcopy(reference.trace)
    mutated["final"]["state"]["variables"]["route"] = "mutated"
    diff = compare_traces(reference.trace, mutated)
    assert not diff.ok
    assert diff.mismatches
