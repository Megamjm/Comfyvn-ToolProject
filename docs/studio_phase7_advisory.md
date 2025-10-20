ComfyVN — Studio Phase 7 (Advisory & Policy)
============================================

Scope
-----
Phase 7 formalises liability gates, advisory scans, and SFW/NSFW filters. The new API stubs allow early integration with the studio UI while keeping the policy rules pluggable.

Subsystem Components
--------------------
- Core logic in `comfyvn/core/advisory.py` manages findings, resolution tracking, and log storage.
- API layer in `comfyvn/server/modules/advisory_api.py` exposes scan, log, and resolve endpoints.
- Advisory logs are intended for `logs/advisory.log` once a dedicated handler is added; for now they flow into `logs/server.log`.
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

Scanner Behaviour
-----------------
- Keyword heuristics currently check for NSFW phrases and license red flags.
- Each finding receives a deterministic `issue_id`, timestamp, and optional detail payload for provenance linking.
- Resolutions flip the `resolved` flag and append notes for audit trails.

Logging & Debugging
-------------------
- Logger name: `comfyvn.advisory` for core logic, `comfyvn.api.advisory` for HTTP entrypoints.
- Manual test sequence:
  1. `curl -X POST http://localhost:8000/api/advisory/scan -H 'Content-Type: application/json' -d '{"target_id":"scene:demo","text":"This line references copyrighted material.","license_scan":true}'`
  2. Call `GET /api/advisory/logs` and verify the issue appears with severity `warn`.
  3. Resolve with `curl -X POST .../resolve -d '{"issue_id":"<id>","notes":"Reviewed and cleared"}'` and confirm the item shows `resolved:true`.
- WARN entries highlight new issues; INFO entries capture scan counts and resolution actions.

Integration Notes
-----------------
- The liability gate can reuse advisory logs by ensuring each required acknowledgement writes a resolved note referencing the acceptance checkbox.
- When SFW/NSFW filters arrive, reuse `AdvisoryIssue.detail` to embed classification probabilities.
- For provenance, the `issue_id` should be stored in `provenance.inputs_json` so exports can trace remediation history.
