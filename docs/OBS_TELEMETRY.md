# Observability & Telemetry

Owners: Project Integration • Audience: Contributors, Modders, Tool Authors

## Intent

Deliver privacy-aware, opt-in telemetry for feature usage, hook sampling, and crash diagnostics without leaking PII. Everything stays local until both the umbrella feature flag and the user consent are set, and identifers are hashed deterministically so dashboards can correlate behaviour without real IDs.

## Feature Flags & Consent

- `features.enable_observability` (default `false`) unlocks the telemetry surface. The legacy key `enable_privacy_telemetry` remains honoured for compatibility.
- `features.enable_crash_uploader` (default `false`) allows crash digests to be registered and included in diagnostics bundles once consent is granted.
- Consent is persisted under `config/comfyvn.json → telemetry`:
  - `telemetry_opt_in` — enables counters & hook sampling.
  - `crash_opt_in` — allows crash digests to be recorded (requires `enable_crash_uploader`).
  - `diagnostics_opt_in` — unlocks diagnostics bundle exports.
  - `dry_run` — keeps telemetry local even when feature flags are enabled.
- Studio's **Settings → Debug & Feature Flags** toggles the flags and writes consent; the `enable telemetry` checkbox updates both `enable_observability` and the legacy alias so older configs continue to work.

## API Surface

Router prefix: `/api/telemetry`

| Endpoint | Description |
| --- | --- |
| `GET /health` | Lightweight status snapshot (`flag_enabled`, consent state, `dry_run`, preview of the anonymised id). Always safe to call. |
| `GET /settings` | Returns persisted consent plus live status booleans. |
| `POST /settings` | Patch consent flags individually (allows disabling without resetting everything). |
| `POST /opt_in` | Convenience helper that enables `telemetry_opt_in` and optionally `crash` / `diagnostics` in one call. |
| `GET /summary` | Full snapshot (features, hooks, crashes, consent) without raw event payloads. |
| `POST /features` | Increment a feature counter (`feature` + optional `variant`). No-op if telemetry is inactive. |
| `POST /events` | Record a structured event. Payload keys containing `id|uuid|path|token|email|user|key|secret|serial|license|address|fingerprint` are hashed automatically. |
| `GET /events?limit=20` | Recent event log (anonymised). |
| `GET /hooks` | Per-hook counters + the last five anonymised payload samples. |
| `GET /crashes` | Hashed crash digests when crash uploads are enabled. |
| `GET /diagnostics` | Exports a scrubbed zip bundle (requires diagnostics opt-in). |

All JSON responses include a `feature_flag` boolean mirroring the umbrella flag so consumers can short-circuit in environments where observability is disabled.

## Diagnostics Bundle

`TelemetryStore.export_bundle()` writes `logs/diagnostics/comfyvn-diagnostics-*.zip` with:

- `manifest.json` — anonymous id, app version, feature flag state, consent block, `dry_run`, and the `telemetry.health()` snapshot.
- `telemetry.json` — the `summary(include_events=True)` payload (features, hooks with samples, anonymised events, crashes, consent metadata).
- `crashes.json` — hashed crash summaries sourced from the crash reporter (event id, exc type, hashed message).

The bundle never includes raw asset ids, file paths, email addresses, or tokens; everything is hashed via `comfyvn/obs/anonymize.py`.

## Debug Hooks & Modder Integrations

- `comfyvn/core/modder_hooks.py` automatically forwards every modder hook through `TelemetryStore.record_hook_event`, capturing counters plus the last five scrubbed payloads per hook. Use `/api/telemetry/hooks` to audit coverage.
- Automation scripts can import `from comfyvn.obs import get_telemetry` and call `record_feature` / `record_event` once telemetry is active. Calls become no-ops when the flag or consent is absent.
- Dry-run (`dry_run=true`) keeps everything local even when feature flags are on; ideal for CI smoke tests.

## Quickstart

```bash
# Check flag + consent state without mutating anything
curl http://127.0.0.1:8001/api/telemetry/health | jq '{flag_enabled, telemetry_active, diagnostics_active, dry_run}'

# Opt in locally (diagnostics on, keep dry-run enabled)
curl -X POST http://127.0.0.1:8001/api/telemetry/opt_in \
     -H 'Content-Type: application/json' \
     -d '{"diagnostics": true, "dry_run": true}'

# Record an event (will be hashed server-side)
curl -X POST http://127.0.0.1:8001/api/telemetry/events \
     -H 'Content-Type: application/json' \
     -d '{"event": "modder.asset.saved", "payload": {"asset_id": "character.hero", "author": "someone@example.com"}}'

# Download the diagnostics bundle
curl -OJ http://127.0.0.1:8001/api/telemetry/diagnostics
```

## Verification Checklist

- [ ] `features.enable_observability` defaults to `false` (`config/comfyvn.json` & `comfyvn/config/feature_flags.py`).
- [ ] `/api/telemetry/health` reports `flag_enabled=false` and `telemetry_active=false` on a fresh install.
- [ ] `POST /api/telemetry/opt_in` with `dry_run=true` flips `telemetry_opt_in` while keeping events local (no crash uploads unless `crash=true`).
- [ ] `/api/telemetry/events` refuses to increment counters when the flag or consent is missing.
- [ ] Diagnostics bundle manifests include the consent block and `health` snapshot, with all sensitive fields hashed (no raw asset ids, emails, tokens, or paths).
- [ ] Settings panel checkbox updates both `enable_observability` and the legacy alias for backwards compatibility.

Refer to `docs/dev_notes_observability_perf.md` for cross-cutting smoke checks shared with the performance budget tooling.
