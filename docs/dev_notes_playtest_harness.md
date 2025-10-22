# Dev Notes — Playtest Harness & Golden Diffs

Updated: 2025-11-24 • Owners: Code Updates + QA

This note documents the deterministic playtest harness introduced in v0.8 for CI, modders, and automation chats. It complements the Scenario Runner docs and integrates with the existing modder hook bus, feature flag matrix, and provenance logging.

## 1. Feature Flag & Entry Points

- Turn on via `config/comfyvn.json → features.enable_playtest_harness` (default `false`). Studio exposes the toggle under **Settings → Debug & Feature Flags**; long-lived processes should call `feature_flags.refresh_cache()` after edits.
- Core modules: `comfyvn/qa/playtest/headless_runner.py` (trace generator) and `comfyvn/qa/playtest/golden_diff.py` (comparison helpers).
- FastAPI router: `comfyvn/server/routes/playtest.py` mounts `POST /api/playtest/run` once the flag is enabled.

## 2. API Surface — `/api/playtest/run`

### Request

```jsonc
{
  "scene": {"id": "demo", "start": "intro", "nodes": [...]},
  "seed": 682,
  "pov": "narrator",
  "variables": {"route": "unset"},
  "prompt_packs": ["POV_REWRITE"],
  "workflow": "ci-smoke",
  "persist": true,
  "dry_run": false
}
```

- `persist=true` writes `<scene>.<seed>.<digest-prefix>.trace.json` and a matching `.log` file under `logs/playtest/`. Set `dry_run=true` (or omit `persist`) to skip filesystem writes.
- `prompt_packs` is optional; the runner canonicalises the list and records it in the trace provenance block.

### Response

```jsonc
{
  "ok": true,
  "digest": "1f6be12f...",
  "persisted": true,
  "dry_run": false,
  "trace": {
    "schema_version": "1.0",
    "meta": {"scene_id": "demo", "seed": 682, "persisted": true, ...},
    "provenance": {"tool": "HeadlessPlaytestRunner", "digest": "1f6be12f..."},
    "steps": [...]
  },
  "trace_path": ".../logs/playtest/demo.682.1f6be12f.trace.json",
  "log_path": ".../logs/playtest/demo.682.1f6be12f.log"
}
```

- `trace.steps[].variables_digest` and `trace.final.variables_digest` allow hash-only comparisons when full payload diffs are noisy.
- `.log` files store a single JSON object (`scene_id`, `seed`, `pov`, `steps`, `digest`, `persisted`) for dashboards that only need run metadata.

## 3. Modder Hooks

Three new events stream playtest telemetry without polling:

| Event | When | Fields |
| --- | --- | --- |
| `on_playtest_start` | Immediately after `initial_state()` | `scene_id`, `seed`, `pov`, `prompt_packs`, `workflow`, `persist`, `variables_digest`, `timestamp` |
| `on_playtest_step` | After each runner `step()` | `scene_id`, `step_index`, `from_node`, `to_node`, `choice_id`, `choice_target`, `choice_text`, `rng_before`, `rng_after`, `variables_digest`, `finished`, `timestamp` |
| `on_playtest_finished` | After trace digest is computed | `scene_id`, `seed`, `pov`, `digest`, `steps`, `aborted`, `persisted`, `timestamp` |

Subscribe via `/api/modder/hooks` (REST or WebSocket) to relay events into dashboards, Discord bots, or CI webhooks.

## 4. Golden Diff Workflow

- Generate a reference trace: `HeadlessPlaytestRunner(log_dir=tmp_path).run(scene, seed=682, persist=True)`.
- Store the resulting `.trace.json` in your suite (e.g., `tests/golden/demo.trace.json`).
- Compare in tests/CI:

  ```python
  from comfyvn.qa.playtest import compare_traces

  golden = json.loads(Path("tests/golden/demo.trace.json").read_text())
  result = runner.run(scene, seed=682, persist=False)
  diff = compare_traces(golden, result.trace)
  diff.raise_for_diff()
  ```

- `diff_traces(..., ignore_paths={"meta.generated_at*"})` supports prefix ignores if suites store custom metadata around the canonical payload.

## 5. Debug & Verification Checklist

- [ ] Enable `features.enable_playtest_harness` and confirm `/api/playtest/run` returns `200` for a dry run.
- [ ] Persist a run (`persist=true`) and verify matching `.trace.json` + `.log` files exist under `logs/playtest/` with identical digest prefixes.
- [ ] Inspect `trace.steps[].rng_before/after` to confirm deterministic seeds when replaying the same `{scene, seed, pov, variables}` payload.
- [ ] Subscribe to `/api/modder/hooks/ws` and ensure the new `on_playtest_*` events stream without errors.
- [ ] Run `pytest tests/test_playtest_headless.py tests/test_playtest_api.py` to validate deterministic traces and API wiring.

## 6. Prompt Pack Notes

- Harness requests accept the existing prompt packs (e.g., `POV_REWRITE`, `NARRATOR_MODE`). The runner records the sorted list in both `meta.prompt_packs` and `provenance.prompt_packs`, enabling golden suites to flag unintended prompt pack changes.
- Feature flags for prompt packs remain independent; enabling the harness does not implicitly enable narrator mode or POV rewrites.

## 7. Troubleshooting

- `HTTP 403` ⇒ feature flag disabled; toggle `enable_playtest_harness` and refresh the cache.
- Missing `.log` file ⇒ request used `dry_run`/`persist=false`; rerun with `persist=true`.
- Digest mismatch ⇒ confirm the scene JSON is canonical (choices require `label` field) and that no external process rewrote the persisted trace.
- Hook payload missing ⇒ check `COMFYVN_LOG_LEVEL=DEBUG` to surface dispatch errors in `logs/server.log` and ensure the harness isn't running in dry-run mode if your automation expects persisted runs.
