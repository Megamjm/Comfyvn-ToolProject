# Dev Notes — P5 Advisory & Bundle Export

Last updated: P5 integration sweep.

## Components

- `comfyvn/advisory/policy.py` — helper around `policy_gate.evaluate_action` that keeps the disclaimer flag in sync with persisted metadata.
- `comfyvn/advisory/scanner.py` — deterministic finding order via keyed dedupe (`issue_id` or `_anon_xxxxxx` fallback).
- `comfyvn/server/routes/advisory.py` — FastAPI surface for the disclaimer banner + advisory scan (`/api/advisory/disclaimer`, `/api/advisory/ack`, `/api/advisory/scan`), guarded by `enable_advisory`.
- `comfyvn/server/routes/export.py` — bundle status probe (`/api/export/bundle/status`) that exposes feature flag and gate evaluation.
- `comfyvn/server/routes/export_public.py` — public exporters (`POST /export/renpy`, `POST /export/bundle`) wrapping the shared orchestrator/helpers and defaulting outputs to the `exports/` tree.
- `scripts/export_bundle.py` — CLI wrapper; enforces `enable_export_bundle`, reports enforcement payload + `log_path`, exit code `3` when the feature flag is disabled.

## API Hooks

- `POST /api/advisory/scan` proxies through `policy_enforcer.enforce`. Use the `include_debug` flag to receive the bundle descriptor emitted to the modder hooks. The route now always returns HTTP 200; callers inspect `findings`/`counts` to decide how to proceed.
- `GET /api/export/bundle/status` provides a quick probe for Studio surfaces to toggle buttons/UX when the flag is off or the disclaimer is still pending.
- `scripts/export_bundle.py` surfaces the enforcement log path (`logs/policy/enforcer.jsonl`) and embeds the disclaimer payload in its JSON output so automation can archive both findings and acknowledgement state.

## Determinism & Provenance

- Advisory findings returned by the scanner are sorted to keep `provenance.json.findings` stable across runs. The remaining provenance payload inherits `generated_at` from the Ren'Py orchestrator; identical scene/timeline inputs produce identical manifests apart from that timestamp.
- If deterministic timestamps become a requirement, consider injecting a hash-based timestamp in `export_api._build_bundle_archive` (not part of this change-set to avoid touching shared exporter code).

## Testing & Verification

- `python tools/check_current_system.py --profile p5_advisory_export --base http://127.0.0.1:8001`
- Manual curl recipes:
  - `curl -s http://127.0.0.1:8001/api/advisory/disclaimer | jq`
  - `curl -s http://127.0.0.1:8001/api/export/bundle/status | jq`
  - `curl -s -X POST http://127.0.0.1:8001/api/advisory/scan -H 'Content-Type: application/json' -d '{"bundle": {"project_id": "demo", "licenses": []}}' | jq`
  - `python scripts/export_bundle.py --project demo --timeline main`

## Follow-ups

- Wire Studio UI to surface the disclaimer banner using `/api/advisory/disclaimer` before enabling the export button.
- Expose `enable_advisory`/`enable_export_bundle` toggles in the settings panel once QA signs off.
- Evaluate whether the Ren'Py orchestrator should provide deterministic `generated_at` values; consider hashing timeline JSON or reusing provenance timestamps from previous runs.
