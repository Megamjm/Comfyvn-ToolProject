ComfyVN — Studio Phase 7 (Advisory & Policy)
============================================

Scope
-----
Phase 7 formalises liability gates, advisory scans, and SFW/NSFW filters. The new API stubs allow early integration with the studio UI while keeping the policy rules pluggable.

See also `docs/development/advisory_modding.md` for contributor-facing guidance on scanner plugins, debug hooks, and legal acknowledgement flows.

Subsystem Components
--------------------
- Core logic in `comfyvn/core/advisory.py` manages findings, resolution tracking, and log storage.
- API layer in `comfyvn/server/modules/advisory_api.py` exposes scan, log, and resolve endpoints.
- Findings persist to the `findings` SQLite table so audits survive process restarts and exports can reference remediation history.
- Advisory logs are intended for `advisory.log` once a dedicated handler is added; for now they flow into `system.log` in the user log directory.
- GUI advisory view will consume `/api/advisory/logs` and surface resolution workflows.

API Hooks
---------
`POST /api/advisory/scan`
  - Request: `{target_id, text, license_scan?}`
  - Response: `{ok, issues:[{issue_id, target_id, kind, severity, message, detail, resolved, timestamp}]}`
  - Rejects empty text with HTTP 400; emits WARN logs for rejected calls.

`GET /api/advisory/logs`
  - Query param `resolved` filters resolved vs unresolved findings.
  - Returns `{ok, items:[...same shape as issues...]}`.

`POST /api/advisory/resolve`
  - Request: `{issue_id, notes?}`
  - Returns `{ok, issue_id}` or HTTP 404 if the issue is unknown.

`GET /api/policy/status`
  - Provides liability-gate status: `{ok, status{ack_legal_v1,requires_ack,ack_timestamp}, message, allow_override}`.
  - When `requires_ack` is true, UI shells should disable export/import triggers until acknowledgement is recorded.

`POST /api/policy/ack`
  - Stores the legal acknowledgement and optional notes. Response mirrors `status`.

`POST /api/policy/evaluate`
  - Returns `{ok, action, requires_ack, warnings[], allow, override_requested}` to surface warnings before exports/imports.

`GET /api/policy/filters`
  - Returns the active content mode (`sfw`, `warn`, or `unrestricted`).

`POST /api/policy/filters`
  - Request `{mode}` to change behaviour. Invalid values return HTTP 400.

`POST /api/policy/filter-preview`
  - Preview the filtered vs flagged items; response includes `allowed`, `flagged`, and `warnings` arrays for GUI display.

Scanner Behaviour
-----------------
- Keyword heuristics currently check for NSFW phrases and license red flags.
- Each finding receives a deterministic `issue_id`, timestamp, and optional detail payload for provenance linking.
- Resolutions flip the `resolved` flag and append notes for audit trails.

Liability Gate & User Choice
---------------------------
- Gate status is stored in `data/settings/config.json` via `comfyvn/core/policy_gate.py`.
- Exports and imports are blocked (`allow=false`) until the legal acknowledgement is recorded; other actions continue to return warnings while permitting the workflow.
- Override requests should capture the user’s identity and notes for auditing.

SFW/NSFW Filters
----------------
- Filter logic lives in `comfyvn/core/content_filter.py` with modes:
  * `sfw`: hides flagged items, logs WARN entries via advisory.
  * `warn`: returns items but marks them with warnings.
  * `unrestricted`: returns everything, still logging INFO/WARN for awareness.
- Flags rely on metadata (`meta.nsfw`, `meta.rating`) and tags containing NSFW keywords.
- GUI flows should pull `warnings` from `filter-preview` to display inline notices while still allowing overrides.

Logging & Debugging
-------------------
- Logger name: `comfyvn.advisory` for core logic, `comfyvn.api.advisory` for HTTP entrypoints.
- Manual test sequence:
  1. `curl -X POST http://localhost:8000/api/advisory/scan -H 'Content-Type: application/json' -d '{"target_id":"scene:demo","text":"This line references copyrighted material.","license_scan":true}'`
  2. Call `GET /api/advisory/logs` and verify the issue appears with severity `warn`.
  3. Resolve with `curl -X POST .../resolve -d '{"issue_id":"<id>","notes":"Reviewed and cleared"}'` and confirm the item shows `resolved:true`.
- WARN entries highlight new issues; INFO entries capture scan counts and resolution actions.
- Policy gate smoke test:
  1. `curl http://localhost:8000/api/policy/status`
  2. `curl -X POST http://localhost:8000/api/policy/ack -H 'Content-Type: application/json' -d '{"user":"tester","notes":"Reviewed"}'`
  3. `curl -X POST http://localhost:8000/api/policy/evaluate -H 'Content-Type: application/json' -d '{"action":"export.bundle","override":true}'`
- Content filter test:
  1. `curl -X POST http://localhost:8000/api/policy/filter-preview -H 'Content-Type: application/json' -d '{"items":[{"id":"asset:1","meta":{"nsfw":true}},{"id":"asset:2","meta":{"tags":["safe"]}}],"mode":"sfw"}'`
  2. Inspect `system.log` in the user log directory for WARN entries referencing `filter_mode`.

Integration Notes
-----------------
- The liability gate can reuse advisory logs by ensuring each required acknowledgement writes a resolved note referencing the acceptance checkbox.
- When SFW/NSFW filters arrive, reuse `AdvisoryIssue.detail` to embed classification probabilities.
- For provenance, the `issue_id` should be stored in `provenance.inputs_json` so exports can trace remediation history.
- Provenance stamping lives in `comfyvn/core/provenance.py` and writes `<file>.prov.json` sidecars plus best-effort PNG/JPEG metadata markers; exports call this helper so Studio and CLI flows share the same audit trail.
