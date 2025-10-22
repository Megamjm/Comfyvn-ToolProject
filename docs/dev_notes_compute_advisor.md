# Dev Notes — Compute Advisor & Scheduler

Date: 2025-12-18  
Owner: Project Integration — Remote Compute & GPU Access

## Summary

- Refined the standalone compute advisor (`comfyvn/compute/advisor.py`) to return optional debug details (pixels, VRAM demand, queue thresholds, contextual notes).
- Added registry statistics and scheduler cost previews so modders can inspect provider metadata and tune rates without diving into code.
- Extended `/api/gpu/list`, `/api/providers`, `/api/compute/advise`, and the new `/api/compute/costs` endpoints with `debug` switches, feature flag context, and safety rails when `features.enable_compute` is disabled.

## Feature Flag Guard

- Default `features.enable_compute = false`. When disabled:
  - `/api/compute/advise` never routes to remote providers (decision falls back to GPU or CPU, reason annotated).
  - `/api/compute/costs` still returns estimates but tags remote queues as informational only.
  - Provider CRUD remains available so teams can stage metadata ahead of enablement.

## Provider Registry

- `ProviderRegistry.stats()` returns `{total, by_kind, storage_path, persisted}` for dashboards.
- Debug responses include the stats block so contributors can confirm persistence.
- Seeds respect `features.enable_compute`; disable the flag to keep remote adapters out of downstream builds.

## Advisor Debug Details

- `choose_device(..., return_details=True)` exposes `thresholds`, `job` derived attributes, and `context` snapshots for QA.
- Remote queue pressure is sourced from `JobScheduler.state()` and injected into the advisor context so we avoid remote suggestions when the remote queue is saturated (depth >= 8).

## Cost Preview

- `JobScheduler.preview_cost()` normalises job specs, applies provider metadata defaults, and emits:
  - `estimate` (rounded total).
  - `breakdown` (minutes, base rate, transfer cost, VRAM surcharge).
  - `hints` (human readable strings).
  - `notes` (always reiterates that no billing flows through ComfyVN).
- `/api/compute/costs` mirrors the response, appends registry stats when `debug=true`, and warns when the feature flag is off.

## QA / Verification

1. Launch the server locally (`python run_comfyvn.py --server-only --server-port 8001`).
2. `curl http://127.0.0.1:8001/api/gpu/list?debug=1` → returns devices, feature context, and raw metrics.
3. `curl http://127.0.0.1:8001/api/compute/advise -d '{"width":1024,"height":1024,"debug":true}'` → decision with debug payload, remote fallback noted when the flag is off.
4. `curl http://127.0.0.1:8001/api/compute/costs -d '{"queue":"remote","duration_minutes":2,"debug":true}'` → cost hints plus `"Remote execution disabled..."` when flag is off.
5. `python tools/check_current_system.py --profile p5_compute_advisor --base http://127.0.0.1:8001` → verifies feature flag default, endpoints, and required docs.

## Follow Ups

- Integrate advisor debug payload into the Studio Compute panel so designers can trace why a job stayed local.
- Surface provider cost metadata in the GUI form fields with inline validation (currency, rate ranges).
- Extend scheduler board output with sticky device affinity markers for remote fleet dashboards.
