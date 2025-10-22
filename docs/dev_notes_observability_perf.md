# Dev Notes — Observability & Performance Budgets

Owners: Project Integration • Audience: Docs/QA channel

## Quick Smoke Checklist

1. Confirm feature defaults are **off**:
   - `jq '.features.enable_observability' config/comfyvn.json` → `false`
   - `jq '.features.enable_perf' config/comfyvn.json` → `false`
2. Hit `/api/telemetry/health` and `/api/perf/health` on a fresh boot. Expect `feature_flag=false`, no consent, empty queues.
3. Run `python tools/check_current_system.py --profile p3_ops_obs_perf --base http://127.0.0.1:8001` — verifies flags, routes, and doc presence (`docs/OBS_TELEMETRY.md`, `docs/PERF_BUDGETS.md`).

## Enabling for Local QA

```bash
# Toggle flags (Studio settings panel does the same)
sed -i 's/"enable_observability": false/"enable_observability": true/' config/comfyvn.json
sed -i 's/"enable_perf": false/"enable_perf": true/' config/comfyvn.json
python - <<'PY'
from comfyvn.config import feature_flags
feature_flags.refresh_cache()
PY

# Consent to telemetry (dry-run keeps everything local)
curl -s -X POST http://127.0.0.1:8001/api/telemetry/opt_in \
  -H 'Content-Type: application/json' \
  -d '{"diagnostics": true, "dry_run": true}' | jq '.health'

# Apply budgets + record profiler mark
curl -s -X POST http://127.0.0.1:8001/api/perf/budgets/apply \
  -H 'Content-Type: application/json' \
  -d '{"max_cpu_percent": 70, "max_running_jobs": 2}' | jq '.limits'
curl -s -X POST http://127.0.0.1:8001/api/perf/profiler/mark \
  -H 'Content-Type: application/json' \
  -d '{"name": "qa.smoke", "category": "tests", "metadata": {"step": "load"}}'
```

## Things to Watch For

- **Consent leakage:** `/api/telemetry/events` must return `{"recorded": false}` when either the feature flag or `telemetry_opt_in` is missing.
- **PII hashing:** Inspect `logs/telemetry/usage.json` and diagnostics bundles; asset IDs, emails, paths, secrets should appear hashed (blake2s hex).
- **Budget soft caps:** registering multiple jobs above the configured limits should produce `queue_state="delayed"` with descriptive reasons (`cpu 85.0%/70.0%`).
- **Profiler health:** `GET /api/perf/health` should surface recent marks/spans once recorded, with `top_time` / `top_memory` arrays populated.
- **Studio toggles:** the Debug & Feature Flags panel updates both umbrella and legacy keys; re-open the JSON to confirm the pairs stay in sync.
- **Hooks:** tail the modder hook stream (`ws://127.0.0.1:8001/api/modder/hooks/ws`) while registering jobs or recording profiler spans—expect `on_perf_budget_state` and `on_perf_profiler_snapshot` events with anonymised payloads.

## Reference Docs

- `docs/OBS_TELEMETRY.md`
- `docs/PERF_BUDGETS.md`
- `docs/development/observability_debug.md`
- `docs/development/perf_budgets_profiler.md`
- `docs/development_notes.md`
