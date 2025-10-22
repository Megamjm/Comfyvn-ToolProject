# Golden Trace Workflow

Updated: 2025-11-30

## Deterministic Runner
- Use `HeadlessPlaytestRunner` (`comfyvn.qa.playtest.headless_runner`). The runner now accepts an optional `worldline` hint and deep-copies any inbound metadata so traces embed the active POV, worldline, workflow, and request metadata across `meta`, `config`, and `provenance`.
- Each trace records an `assets` manifest collected from every node/choice/action visited. The manifest is mirrored into the persisted `.log` files and surfaced via modder hooks so contributors can diff asset usage without opening the JSON.
- Modder hooks (`on_playtest_start`, `on_playtest_step`, `on_playtest_finished`) now include `worldline`, `metadata`, and `assets` keys alongside the deterministic timestamps that already ship with the harness.
- Persisted summaries (`PlaytestRun.write`) include the worldline and asset manifest and retain the canonical filename pattern `<scene>.<seed>.<digest-prefix>.trace.json`.

## POV Suites & Golden Artifacts
- `HeadlessPlaytestRunner.run_per_pov_suite(plan, *, seed_offset=0, persist=True, workflow=None, golden_dir=None)` executes the canonical linear/choice-heavy/battle trio (or any caller-defined buckets) for every POV in the `plan`.
- Plan shape:
  ```
  {
      "pov_id": {
          "category": {
              "scene": <scene_dict>,
              "seed": 3,                 # optional override
              "variables": {...},        # optional
              "worldline": "wl.live",    # optional
              "prompt_packs": [...],     # optional
              "metadata": {...},         # optional merges with {"category", "pov"}
          }
      }
  }
  ```
  Supplying a raw scene dict (no wrapper) still works for simple cases.
- When `golden_dir` is provided (recommended: `comfyvn/qa/goldens/<pov>/<category>/`), the suite writes deterministic traces and logs into that directory while leaving the runner’s log directory untouched.
- Example:

```python
from pathlib import Path
from comfyvn.qa.playtest.headless_runner import HeadlessPlaytestRunner

runner = HeadlessPlaytestRunner()
suite_plan = {
    "mc": {
        "linear": {"scene": scene_linear},
        "choice": {
            "scene": scene_branchy,
            "seed": 5,
            "worldline": "wl.mc.branch",
            "metadata": {"tags": ["branching", "dialogue"]},
        },
        "battle": {"scene": scene_battle, "variables": {"starting_hp": 42}},
    },
    "rival": {
        "linear": scene_rival_linear,
        "choice": {"scene": scene_rival_choice, "seed": 8},
        "battle": {"scene": scene_rival_battle, "prompt_packs": ["BATTLE_AI"]},
    },
}

runner.run_per_pov_suite(
    suite_plan,
    seed_offset=100,
    workflow="ci-goldens",
    persist=False,
    golden_dir=Path("comfyvn/qa/goldens"),
)
```

## Golden Diff Tool
- `golden_diff.compare_traces(expected, actual, ignore_paths=None)` continues to compare two in-memory traces, while `golden_diff.compare_trace_files(expected_path, actual_path, ignore_paths=None)` handles the load-and-compare path for CI scripts.
- Diff messages now call out the exact surface that drifted: e.g. `step 7 choice id changed`, `step 12 transitions to different node`, `asset manifest 'music' entries changed`, or `trace worldline changed`.
- Continue to ignore regenerated digests by passing `ignore_paths={"provenance.digest"}` (wildcards such as `"meta.generated_at*"` are still respected).
- Example assertion helper:

```python
from comfyvn.qa.playtest.golden_diff import compare_trace_files

result = compare_trace_files(
    "comfyvn/qa/goldens/mc/choice/demo_scene.5.1f6be12f.trace.json",
    "tmp/playtest/demo_scene.5.latest.trace.json",
    ignore_paths={"provenance.digest"},
)
result.raise_for_diff()
```

## Make / CI Snippet
- Minimal target for local or CI runs (adjust paths to match your suite):

```make
# Makefile
.PHONY: golden-test
golden-test:
	python - <<'PY'
from pathlib import Path
from comfyvn.qa.playtest.headless_runner import HeadlessPlaytestRunner
from suite_plan import PLAN  # import your plan definition

runner = HeadlessPlaytestRunner()
runner.run_per_pov_suite(
    PLAN,
    seed_offset=0,
    workflow="ci-goldens",
    persist=False,
    golden_dir=Path("comfyvn/qa/goldens"),
)
PY
	pytest tests/test_playtest_headless.py tests/test_playtest_api.py
```

- Verify backend parity via the existing checker once the harness is wired into the server:  
  `python tools/check_current_system.py --profile p2_golden --base http://127.0.0.1:8001`

## Storage & Naming
- Canonical goldens live under `comfyvn/qa/goldens/<pov>/<category>/`. Each run produces both `.trace.json` and `.log` files keyed by `<scene>.<seed>.<digest[:12]>`.
- Logs now include `worldline`, `asset_manifest`, and step counts so dashboards can diff metadata without opening the full trace.
- Set `persist=False` when running suites inside CI scratch space; passing `golden_dir` still writes the desired artifacts for comparison.

## Troubleshooting
- Digest drift now accompanies targeted messages—pay attention to `step N index changed (order drift)` or `asset manifest 'backgrounds' entries changed` to narrow down regressions quickly.
- Worldline mismatches (`trace worldline changed`, `config worldline changed`) usually indicate routing bugs or misconfigured overrides; confirm the plan-provided worldline or backend response.
- Asset discrepancies are collected per-node; if an expected sprite is missing, inspect `trace["assets"]["sprites"]` for the recorded values.
- When scenes depend on RNG (combat, loot), keep per-category seeds stable inside the suite plan to avoid unintentional drift.
