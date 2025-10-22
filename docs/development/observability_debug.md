# Observability & Debugging Cheatsheet

Owner: Project Integration • Audience: Contributors, Modders, CI

## 1. Crash Reporter

- Module: `comfyvn/obs/crash_reporter.py`
- FastAPI boot installs the crash hook automatically (`install_sys_hook()`).
- Manual capture: `capture_exception(exc, context={"plugin": "asset_sync"}, attach=[path])` writes a JSON dump to `logs/crash/crash-YYYYMMDD_HHMMSS-<id>.json`.
- Dump fields include UTC timestamp, process id, working directory, traceback, optional context, and attachment paths.
- Surfacing tips:
  * GUI panels can link to the file path returned by `capture_exception`.
  * CLI tools should print the report path on stderr so CI surfaces pick it up.
  * Use the `"context"` object to stamp plugin ids, job ids, or modder handles for later triage.

## 1.5 Telemetry & Diagnostics

- Modules: `comfyvn/obs/anonymize.py` (hash helpers) and `comfyvn/obs/telemetry.py` (opt-in `TelemetryStore`).
- Feature flags: set `features.enable_observability` (legacy `enable_privacy_telemetry`) / `features.enable_crash_uploader` to `true` in `config/comfyvn.json` (or via Settings → Debug & Feature Flags). Consent lives in the adjacent `telemetry` block (`telemetry_opt_in`, `crash_opt_in`, `diagnostics_opt_in`, `dry_run`).
- Opt-in via REST:
  ```bash
  curl -X POST http://127.0.0.1:8001/api/telemetry/opt_in \
       -H "Content-Type: application/json" \
       -d '{"diagnostics": true, "dry_run": true}'
  ```
- Inspect counters & health:
  ```bash
  curl http://127.0.0.1:8001/api/telemetry/health | jq '{flag_enabled, telemetry_active, diagnostics_active}'
  curl http://127.0.0.1:8001/api/telemetry/summary | jq '{id: .anonymous_id, telemetry: .telemetry_active, features: .features}'
  curl http://127.0.0.1:8001/api/telemetry/hooks | jq '.hooks["on_asset_registered"]'
  ```
- Record a custom event (payload keys containing `id|uuid|path|token|email|user|key|secret|serial|license|address|fingerprint` are auto-hashed):
  ```bash
  curl -X POST http://127.0.0.1:8001/api/telemetry/events \
       -H "Content-Type: application/json" \
       -d '{"event":"modder.asset.packaged","payload":{"uid":"abc123","path":"mods/hero.png"}}'
  ```
- Diagnostics bundle (`GET /api/telemetry/diagnostics`) returns a zip with `manifest.json` (anonymous id, version, feature flag, consent, health snapshot), `telemetry.json` (feature counters, hook samples, recent events), and `crashes.json` (hashed crash summaries). Files are emitted under `logs/diagnostics/comfyvn-diagnostics-*.zip`.
- Programmatic access: `from comfyvn.obs import get_telemetry, anonymize_payload`; call `get_telemetry().record_feature("toolkit.launch")` to increment counters from local scripts once telemetry is enabled.

## 2. Structured Logging Adapter

- Module: `comfyvn/obs/structlog_adapter.py`
- Usage: `log = get_logger("asset.registry", component="asset-registry"); log.info("sidecar-updated", extra={"path": str(sidecar)})`.
- `bind()` and `unbind()` mirror structlog ergonomics without extra dependencies.
- Output format:
  ```json
  {"component": "asset-registry", "event": "sidecar-updated", "logger": "asset.registry", "path": "...", "timestamp": "2025-10-21T23:17:45.123456+00:00"}
  ```
- Best practices for modders:
  * Bind constant context (`log = log.bind(modder="sprite-kit")`) before emitting rapid-fire events.
  * Keep values JSON-coercible; non-serialisable objects fall back to `repr()`.
  * Respect user log directories by honouring `COMFYVN_RUNTIME_ROOT` or `COMFYVN_LOG_DIR`.

## 3. Doctor Phase 4

- Entry point: `python tools/doctor_phase4.py --base http://127.0.0.1:8000`.
- Checks:
  * `/health` probe (fails gracefully if the server is offline).
  * Crash simulation via `capture_exception`.
  * Structured log emission test.
- Output: JSON report printed to stdout, exit code `0` on success, `1` on failure.
- CI integration: Add to smoke workflows after bootstrapping a dev server; capture the JSON blob for artefacts.
- Local workflow: Run after installing extensions or modding hooks to verify crash dumps/logging still work.

## 4. Asset Registry Hooks & Debug APIs

- Registry API: `comfyvn/studio/core/asset_registry.py` exposes `add_hook(event, callback)` for `asset_registered`, `asset_meta_updated`, `asset_removed`, and `asset_sidecar_written`.
- REST endpoints:
  * `GET /assets` with filters (`type`, `tags`, `licenses`) for dashboards and modder scripts.
  * `POST /assets/register` accepts metadata, provenance, and optional sidecar definitions.
  * `POST /assets/upload` handles file uploads (returns asset ids plus storage paths).
  * `GET /assets/{asset_id}/download` serves raw files, respecting provenance guards.
- Debug helpers:
  * Enable verbose logs: `COMFYVN_LOG_LEVEL=DEBUG`.
  * Force registry rebuilds with sidecar auditing: `python comfyvn/registry/rebuild.py --enforce-sidecars`.
  * Stand-alone audit tool: `python tools/assets_enforcer.py --report --dry-run`.
- Extension writers should register hooks in their plugin init to stay in sync with sidecar updates and log diff results via the structured adapter.

## 5. Debug Integrations Panel & Hook Bus

- Studio → System → **Debug Integrations** opens the provider diagnostics widget (`comfyvn/gui/panels/debug_integrations.py`). It polls `/api/providers/health` and `/api/providers/quota?id=…` every 15 s (toggleable) to surface uptime, quota/credit snapshots, and the masked provider config pulled from `ComputeProviderRegistry.list()`.
- Use the panel when onboarding new API keys or debugging remote failures. Green rows indicate healthy providers; amber rows appear when latency warnings surface; red rows include the last error plus timestamp so you can cross-check `logs/server.log`.
- CLI parity:
  ```bash
  curl -s http://127.0.0.1:8001/api/providers/health | jq '.results[] | {id: .provider_id, ok, error, latency_ms}'
  curl -s "http://127.0.0.1:8001/api/providers/quota?id=runpod" | jq
  ```
- Modder hook bus endpoints (see also `docs/dev_notes_modder_hooks.md`):
  * `GET /api/modder/hooks` → spec + recent history + current webhook registrations.
  * `GET /api/modder/hooks/history?limit=10` → rolling event log for CLI smoke tests.
  * `POST /api/modder/hooks/webhooks` → register outbound HTTP callbacks (`{"event": "on_asset_meta_updated", "url": "https://example/hook", "secret": "optional"}`), signatures arrive in `X-Comfy-Signature` (HMAC SHA-256).
  * `ws://127.0.0.1:8001/api/modder/hooks/ws` → stream events (`{"event":"on_scene_enter","ts":...,"data":{...}}`).
  * `dev/modder_hooks/` + `COMFYVN_DEV_MODE=1` enable inline Python plugins that receive hook callbacks without HTTP.

## 6. Golden Contract Tests

- Location: `tests/e2e/test_scenario_flow.py`.
- Coverage: `/api/scenario/*`, `/api/save/*`, `/api/presentation/plan`, `/api/export/*`.
- Normalisation: dynamic fields (timestamps, runtime roots, bundle names) are replaced with placeholders before comparison to `tests/e2e/golden/phase4_payloads.json`.
- Workflow:
  1. Run `pytest tests/e2e/test_scenario_flow.py` after altering API payloads.
  2. If expectations change intentionally, regenerate the golden JSON (`/tmp/phase4_golden.json` helper script) and copy it into `tests/e2e/golden/`.
  3. Update the changelog so downstream modders know to refresh their tooling expectations.

## 7. Quick Reference & Links

- Crash dumps: `logs/crash/*.json`
- Telemetry counters: `logs/telemetry/usage.json`
- Diagnostics bundles: `logs/diagnostics/comfyvn-diagnostics-*.zip`
- Telemetry API: `/api/telemetry/{summary,settings,events,features,hooks,crashes,diagnostics,health,opt_in}`
- Structured log output: `logs/run-*/run.log` (JSON lines)
- Doctor script: `tools/doctor_phase4.py`
- Asset registry hooks: `comfyvn/studio/core/asset_registry.py`
- Modder docs: `docs/development/plugins_and_assets.md`, `docs/development/advisory_modding.md`
- Observability checklist owner: Project Integration (ping in Docs channel for updates)
