# Performance Budgets & Profiler Notes

Last updated: 2025-11-14 • Owners: Performance & Observability Chats

This note documents the CPU/VRAM budgeting system, lazy asset eviction helpers, and the profiler dashboard so modders, automation scripts, and Studio panels can integrate without reverse-engineering the backend.

## Feature Flags

- `config/comfyvn.json → features.enable_perf` (default `false`) is the umbrella toggle for budget throttling and the profiler dashboard. Flip it via **Settings → Debug & Feature Flags** or patch the JSON, then call `feature_flags.refresh_cache()` when toggling at runtime.
- Legacy flags `enable_perf_budgets` / `enable_perf_profiler_dashboard` remain honoured for backwards compatibility; enabling them individually also activates the respective subsystems.
- External deployments should keep these flags **OFF** by default; integrations can enable them locally to test queue behaviour before rolling out instrumentation.

## Budget Manager API

Router prefix: `/api/perf/budgets`

| Endpoint | Description |
| --- | --- |
| `GET /budgets` | Snapshot of limits, live metrics, queued/delayed job ids, and registered lazy assets. |
| `POST /budgets/apply` | Update limits (`max_cpu_percent`, `max_mem_mb`, `max_vram_mb`, `max_running_jobs`, `max_queue_depth`, `lazy_asset_target_mb`, `evaluation_interval`). |
| `POST /budgets/jobs/register` | Register a submission. Include a `perf` block in the payload (e.g. `{ "perf": { "cpu_percent": 12, "ram_mb": 1024, "vram_mb": 2048 } }`) so the manager can evaluate resource pressure. Returns `{queue_state, reason}` where `queue_state` is `queued` or `delayed`. |
| `POST /budgets/jobs/start` | Promote a job to `running`. Call this when a worker takes ownership to keep the job cap accurate. |
| `POST /budgets/jobs/finish` | Mark jobs `complete`, `canceled`, or `error` and free capacity. |
| `POST /budgets/jobs/refresh` | Force a re-evaluation of delayed jobs against current metrics; returns a list of transition envelopes. |
| `POST /budgets/assets/register` | Register a lazily loaded asset (`asset_id`, `size_mb`, metadata). |
| `POST /budgets/assets/touch` | Mark an asset as recently used so it remains loaded. |
| `POST /budgets/assets/evict` | Force eviction (LRU order) targeting the requested MB. |

`GET /api/perf/health` (umbrella route) returns the aggregated health snapshot, echoing `feature_flag`, budget queue counts, and the profiler's top offenders for smoke checks.

Sample cURL to set limits and register a job:

```bash
curl -s -X POST http://127.0.0.1:8000/api/perf/budgets/apply \
  -H 'Content-Type: application/json' \
  -d '{"max_cpu_percent": 75, "max_mem_mb": 20480, "max_running_jobs": 2}'

curl -s -X POST http://127.0.0.1:8000/api/perf/budgets/jobs/register \
  -H 'Content-Type: application/json' \
  -d '{"job_id": "render-1024", "job_type": "render", "payload": {"scene": "intro", "perf": {"cpu_percent": 12, "ram_mb": 1536, "vram_mb": 2048}}}'
```

When queues exceed limits the manager delays jobs gracefully (`queue_state=delayed`, `reason` explains the constraint). Poll `/jobs/poll` or call `/budgets/jobs/refresh` to see ready transitions once metrics fall back within budget.

## Lazy Asset Eviction

- Register assets with `POST /budgets/assets/register` supplying `size_mb` so the manager can approximate memory pressure.
- Touch assets whenever they are accessed to update the last-used timestamp.
- When RAM/VRAM usage exceeds configured budgets, the manager automatically evicts least-recently-used assets until it frees `lazy_asset_target_mb`. The optional unload handler can be wired from Python with `budget_manager.set_api_asset_unload_handler(...)`.
- Evictions emit Modder hook envelopes (see below) so automation scripts can track unloads and reload assets opportunistically.

## Profiler API

Router prefix: `/api/perf/profiler`

| Endpoint | Description |
| --- | --- |
| `POST /mark` | Emit an instant mark (`name`, `category`, optional metadata). |
| `GET /dashboard?limit=5` | Aggregate spans and marks, returning top offenders by time and memory, grouped by category. |
| `POST /reset` | Clear history and aggregates. |

`PerfProfiler.profile(name, category)` is exposed to Python callers via `from comfyvn.perf import perf_profiler`. Example usage:

```python
from comfyvn.perf import perf_profiler

with perf_profiler.profile("hydrate_scene", category="render", metadata={"scene": sid}):
    hydrate_scene_graph(sid)
```

Marks and spans feed the dashboard and power the Modder hook stream for external dashboards.

## Modder Hooks & Events

- `on_perf_budget_state` — fired for budget limit updates, job transitions (`job.registered`, `job.started`, `job.finished`), queue refreshes, and lazy asset evictions. Payload includes `{trigger, payload, timestamp}` with queue state or eviction details.
- `on_perf_profiler_snapshot` — broadcasts profiler marks, span records, dashboard snapshots, and resets. Payload includes `{trigger, payload, timestamp}`; dashboards expose `top_time`, `top_memory`, grouped aggregates, and recent marks.

Subscribe via `/api/modder/hooks` (REST history), `/api/modder/hooks/ws` (WebSocket), or register in-process listeners via `comfyvn.core.modder_hooks.register_listener`.

## Logging

- Server logs (`logs/server.log`, logger `comfyvn.server.routes.perf`) record limit updates, queue decisions, and lazy asset evictions at INFO level.
- Budget/autoevict debugging uses the module logger `comfyvn.perf.budgets`. Set `COMFYVN_LOG_LEVEL=DEBUG` to inspect evaluation decisions.
- Profiler activity logs under `comfyvn.perf.profiler` when marks and spans are recorded.

## Integration Notes

- The `/jobs` REST API automatically annotates submissions with budget status when `enable_perf` (or legacy `enable_perf_budgets`) is on. Consumers should respect `status=delayed` and poll for transitions before dispatching work.
- Workers should call `POST /api/perf/budgets/jobs/start` before executing a job and `POST /api/perf/budgets/jobs/finish` afterward to keep caps accurate. Jobs that bypass the helper risk over-scheduling when hosts are saturated.
- Studio panels can call `/api/perf/profiler/dashboard` to render live charts; the response is structured for quick ingestion by charting libraries (`top_time`, `top_memory`, per-category aggregates, recent marks).
- Automation scripts can inject custom unload handlers by calling `budget_manager.set_api_asset_unload_handler(...)` at startup, ensuring lazy eviction hooks tie into their asset cache or on-demand loader.
