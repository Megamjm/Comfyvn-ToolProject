# Performance Budgets & Profiler

Owners: Performance & Observability Chats • Audience: Contributors, Tooling Authors, CI

## Intent

Provide soft CPU/RAM/VRAM limits, job caps, and lightweight profiling so large renders do not starve shared hosts. Budgets are opt-in and expose debug hooks/API endpoints for modders while keeping defaults safe for production.

## Feature Flags

- `features.enable_perf` (default `false`) enables both the budget manager and the profiler dashboard.
- Legacy keys `enable_perf_budgets` / `enable_perf_profiler_dashboard` remain supported; enabling either also activates the respective subsystem.
- Keep the flags **OFF** in production builds unless you have explicit consent from contributors to collect perf metadata.

## API Surface

Router prefixes: `/api/perf/budgets`, `/api/perf/profiler`, umbrella `/api/perf/health`

| Endpoint | Description |
| --- | --- |
| `GET /health` | Combined snapshot (flag state, queue counts, lazy asset totals, `PerfProfiler.health()` top offenders). Always available for smoke tests. |
| `GET /budgets` | Snapshot of limits, metrics, queued/delayed ids, running jobs, and registered lazy assets. |
| `POST /budgets/apply` | Patch limits (`max_cpu_percent`, `max_mem_mb`, `max_vram_mb`, `max_running_jobs`, `max_queue_depth`, `lazy_asset_target_mb`, `evaluation_interval`). |
| `POST /budgets/jobs/{register,start,finish,refresh}` | Manage job lifecycle; registrations include optional `payload.perf` hints so the manager can evaluate pressure. |
| `POST /budgets/assets/{register,touch,evict}` | Track lazy assets and trigger LRU evictions. |
| `POST /profiler/mark` | Emit an instant mark (`name`, `category`, metadata). |
| `GET /profiler/dashboard` | Aggregated spans/marks, top offenders by time/memory, category slices. |
| `POST /profiler/reset` | Clear profiler history.

All responses include a `feature_flag` boolean so tooling can bail out gracefully when the subsystem is disabled.

## Hooks & Automation

- Budget manager emits `on_perf_budget_state` for limit updates, job transitions, queue refreshes, and asset evictions. Payloads include `{trigger, payload, timestamp}`.
- Profiler emits `on_perf_profiler_snapshot` for marks, span records, dashboard snapshots, and resets.
- Import helpers: `from comfyvn.perf import budget_manager, perf_profiler`. Scripts can register lazy assets or custom unload handlers, and profile hot paths via `with perf_profiler.profile("step", category="render")`.
- `BudgetManager.health()` and `PerfProfiler.health()` power `/api/perf/health`; both are safe to call from smoke scripts without mutating queue state.

## Quickstart

```bash
# Check feature flag + queue health
curl http://127.0.0.1:8001/api/perf/health | jq '{feature_flag, budgets_enabled, profiler_enabled, budgets: .budgets.queue}'

# Apply a tighter local budget
curl -X POST http://127.0.0.1:8001/api/perf/budgets/apply \
     -H 'Content-Type: application/json' \
     -d '{"max_cpu_percent": 70, "max_running_jobs": 2, "lazy_asset_target_mb": 1024}'

# Register a job with resource hints
curl -X POST http://127.0.0.1:8001/api/perf/budgets/jobs/register \
     -H 'Content-Type: application/json' \
     -d '{"job_id": "render-01", "job_type": "render", "payload": {"perf": {"cpu_percent": 10, "ram_mb": 1024, "vram_mb": 2048}}}'

# Inspect profiler top offenders
curl http://127.0.0.1:8001/api/perf/profiler/dashboard?limit=5 | jq '.dashboard.top_time'
```

## Verification Checklist

- [ ] `features.enable_perf` defaults to `false` (`config/comfyvn.json` & `comfyvn/config/feature_flags.py`).
- [ ] `/api/perf/health` reports `feature_flag=false` and `budgets_enabled=false` on a fresh install.
- [ ] Budget endpoints return `403` until the feature flag is enabled.
- [ ] `BudgetManager.health()` reflects queue counts and asset totals; `PerfProfiler.health()` returns top offenders when spans exist.
- [ ] Modder hooks `on_perf_budget_state` / `on_perf_profiler_snapshot` fire with anonymised payloads (no raw file paths or secrets).
- [ ] Studio settings toggle updates both `enable_perf` and the legacy keys to keep older configs in sync.
- [ ] Smoke check `python tools/check_current_system.py --profile p3_ops_obs_perf` passes (flags false, routes present, docs available).

Refer to `docs/dev_notes_observability_perf.md` for joint observability + perf QA drills.
