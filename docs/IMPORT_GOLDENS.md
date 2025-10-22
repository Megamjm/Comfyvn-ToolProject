# Visual Novel Import Golden Traces

The `p9_golden_import_tests` profile locks deterministic behaviour for the
Story Tavern → VN builder → headless playtest pipeline. The test suite feeds a
sample transcript through `/api/import/st/start`, builds a temporary VN project
via `/api/vn/build`, and records canonical playtest traces from
`/api/playtest/run`. These traces are compared against the fixtures stored under
`qa/goldens/vn_st_sample/`.

## Directory Layout

| Path | Purpose |
| --- | --- |
| `qa/fixtures/st_sample.json` | Minimal MC vs. Antagonist transcript used by the test harness. |
| `qa/goldens/vn_st_sample/trace_mc.json` | Headless trace for the main-character POV. |
| `qa/goldens/vn_st_sample/trace_antagonist.json` | Headless trace for the antagonist POV. |
| `tests/vn/test_st_loader.py` | End-to-end test that orchestrates import → build → play and compares against the golden traces. |

## Regenerating Goldens

Run the helper baked into the test module whenever the ST mapping rules or VN
builder output changes:

```bash
python tests/vn/test_st_loader.py
pytest -q -k st_loader
```

The script replays the pipeline using a temporary workspace, writes updated
traces into `qa/goldens/vn_st_sample/`, and the pytest invocation verifies that
the new goldens match the deterministic trace emitted by the headless runner.

## Debugging Tips

- The importer writes intermediate artefacts to the patched `IMPORT_ROOT`
  (`/tmp/.../imports/<run_id>/`) while the test runs. Inspect
  `scenes.json` or `preview.json` there if you need to compare raw mapper output.
- The headless runner digest is included in each golden file under `trace.digest`.
  When the digest moves unexpectedly, regenerate the goldens and review the
  diff to confirm the new trace matches the intended scenario flow.
