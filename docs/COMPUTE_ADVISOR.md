# Compute Advisor & Scheduler

The compute advisor surfaces local hardware snapshots, a persisted provider registry, scheduling helpers, and cost-only previews so Studio tooling and modders can route jobs without guessing. Everything is disabled by default via `features.enable_compute = false`; flip it on only when you are ready to offload work to remote GPUs.

## FastAPI Surface

| Route | Method | Description |
| ----- | ------ | ----------- |
| `/api/gpu/list` | `GET` | Enumerates local CPU + NVIDIA GPUs and returns summarised metrics (`mem_total`, `mem_free`, `util`). Append `?debug=1` to inspect the raw device list and system payload captured from `collect_system_metrics()`. |
| `/api/providers` | `GET` | Lists persisted compute providers from `config/compute_providers.json`. Add `?debug=1` to include aggregate counts and storage metadata. |
| `/api/providers` | `POST` | Registers or updates a provider entry (`{id, kind, base, meta}`), persisting to disk and returning the stored record. Include `"debug": true` in the body to get updated stats alongside the upserted entry. |
| `/api/providers/{id}` | `DELETE` | Removes a provider entry. Add `?debug=1` for an updated stats snapshot after deletion. |
| `/api/compute/advise` | `POST` | Heuristic advisor returning `{decision, reason, target}` plus a context summary. Send `"debug": true` to receive thresholds, derived job values, scheduler queue counts, hardware metrics, and registry stats. |
| `/api/compute/costs` | `POST` | Lightweight cost preview that never bills. Accepts the same job payload as `enqueue` and responds with `{estimate, breakdown, hints, notes}`. `"debug": true` echoes provider stats and the resolved registry entries. |

All responses include `{"feature": {"feature": "enable_compute", "enabled": false}}` so clients can reflect flag state. When the feature remains disabled, remote suggestions fall back to GPU or CPU automatically and the cost endpoint annotates remote estimates as informational only. GPU policy preferences now persist inside the shared settings store (`settings/config.json` + SQLite), so CLI tools and the GUI share the same `{"mode", "preferred_id", "manual_device"}` snapshot without chasing `gpu_policy.json`.

## Payload Examples

### Advising a Job

```bash
curl -s -X POST "$BASE/api/compute/advise" \
  -H "Content-Type: application/json" \
  -d '{
    "job": {"width": 2048, "height": 1152, "priority": 3},
    "allow_remote": true,
    "debug": true
  }'
```

Response highlights:

- `decision` and `reason` summarise the selected path.
- `target` normalises the action into `cpu`, `gpu`, or `remote` regardless of the underlying device string.
- `context` captures GPU presence, queue depths, and VRAM headroom.
- `debug.advisor.thresholds` lists the cut-offs for queue pressure, image size, and VRAM slack.
- `debug.scheduler.queues` mirrors the active queue lengths so modders can monitor saturation.

### Previewing Cost

```bash
curl -s -X POST "$BASE/api/compute/costs" \
  -H "Content-Type: application/json" \
  -d '{
    "job": {
      "queue": "remote",
      "provider_id": "runpod-dev",
      "duration_minutes": 4.5,
      "bytes_tx": 1073741824,
      "bytes_rx": 67108864,
      "vram_gb": 16
    },
    "debug": true
  }'
```

Key fields:

- `estimate.estimate` is the rounded total in the provider currency (defaults to USD).
- `estimate.breakdown` surfaces base, transfer, and VRAM components.
- `estimate.hints[]` reads like a human explanation of each component.
- `estimate.notes[]` always reiterates that nothing is billed through ComfyVN.
- `debug.providers` lists the stored registry entries so contributors can confirm metadata.

## Provider Registry

- Backing store: `config/compute_providers.json`.
- Seed sources: `config/comfyvn.json` (when `features.enable_compute` is true) and `comfyvn.json` in the repo root.
- Default helper: `ProviderRegistry.stats()` returns `{"total": count, "by_kind": {"runpod": 2, ...}, "storage_path": "..."}` and is emitted whenever `debug` is enabled.

`meta` is an open dictionary. Suggested keys:

- `cost_per_minute` (float) — base rate used by the cost preview.
- `egress_cost_per_gb` / `ingress_cost_per_gb` — transfer rates.
- `vram_cost_per_gb_minute` — VRAM metering rate when applicable.
- `pricing_url` and `notes` — copied into API responses to guide users.

## Scheduler Helpers

`JobScheduler.preview_cost()` drives `/api/compute/costs`. It normalises job specs, applies provider metadata defaults, and returns both machine-friendly numbers and human-readable hints. The existing scheduler routes remain available under `/api/schedule/*` for dashboards:

- `/api/schedule/state` — queues + active jobs.
- `/api/schedule/board` — timeline segments suitable for Gantt charts.
- `/api/schedule/enqueue|claim|complete|fail|requeue` — testing and automation hooks.

## Modder & Debug Flows

- Use `debug=true` on any compute endpoint to introspect advisor thresholds, system metrics, provider stats, and cost breakdowns without attaching a debugger.
- The compute advisor declines remote execution when the feature flag is off, leaking a clear note in `reason`. Studio UI can surface the same note to prompt users to enable the feature explicitly.
- CI-safe profiling: run `python tools/check_current_system.py --profile p5_compute_advisor --base http://127.0.0.1:8001` to verify flag defaults, endpoints, and documentation coverage without hitting remote providers.

## Related References

- `comfyvn/compute/providers.py` — JSON-backed registry with thread-safe CRUD helpers.
- `comfyvn/compute/advisor.py` — heuristic decision maker with optional debug details.
- `comfyvn/compute/scheduler.py` — job queues, sticky device support, cost previews, scheduler REST bridge under `/api/schedule/*`.
- `docs/dev_notes_compute_advisor.md` — development log, hook recipes, and test hints.
- A lightweight HTTP echo adapter (`kind="remote"`, `service="echo"`) is available for smoke tests. Health checks hit `GET <base>/health` when a real URL is provided, and when using `stub://` or `memory://` bases the adapter returns `{ok:true}` without leaving the process. Quota/template routes reply with a simple `"unsupported"` payload so dashboards stay predictable.
