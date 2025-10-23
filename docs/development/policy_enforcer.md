# Policy & License Enforcer

Date: 2025-10-22  
Owner: Advisory/Policy team

## Overview

`comfyvn/policy/enforcer.py` centralises the import/export gate logic. Every high-risk action (`import.chat`, `import.manga`, `import.vn`, `export.renpy`, `export.bundle`, `export.scene`) now executes the enforcer before writing to disk. Findings are sourced from the advisory scanner; `block`-level entries still surface in the results, but callers decide how to react (the API no longer returns HTTP `423`).

Feature flag `enable_policy_enforcer` (default `true`) controls the wiring. Disable the flag in `config/comfyvn.json → features` to retain legacy behaviour during migrations or offline smoke tests.

## REST API

### POST `/api/policy/enforce`

Input payload:

```json
{
  "action": "export.bundle",
  "bundle": {
    "project_id": "demo-project",
    "timeline_id": "main",
    "metadata": {"source": "docs-example"}
  },
  "override": false
}
```

Sample response when the bundle is clear:

```json
{
  "ok": true,
  "result": {
    "allow": true,
    "counts": {"info": 0, "warn": 0, "block": 0},
    "log_path": "logs/policy/enforcer.jsonl",
    "findings": [],
    "gate": {"requires_ack": false, "ack_legal_v1": true, "override_requested": false},
    "bundle": {"project_id": "demo-project", "timeline_id": "main", "source": "docs-example"}
  }
}
```

If any finding reports `level: block`, the `result.blocked` array is populated and `counts.block` increments. Callers should surface these blockers to reviewers and decide whether to pause the workflow or proceed with manual overrides.

### GET `/api/policy/audit`

Parameters:

- `limit` (default 50) — number of events returned, newest first.
- `action` (optional) — filter events to a specific policy action.
- `export` (`0|1`) — when truthy, writes a timestamped JSON report (`logs/policy/policy_audit_<ts>.json`) and returns its path under `report.path`.

Response structure:

```json
{
  "ok": true,
  "events": [
    {
      "action": "export.bundle",
      "allow": true,
      "counts": {"info": 0, "warn": 1, "block": 0},
      "timestamp": 1732212345.12,
      "source": "export.bundle",
      "log_path": "logs/policy/enforcer.jsonl",
      "bundle": {"project_id": "demo-project"},
      "warnings": [{"message": "License 'CC-BY-NC-4.0' may restrict usage."}]
    }
  ],
  "summary": {
    "events": 12,
    "totals": {"info": 4, "warn": 7, "block": 1},
    "per_action": {"export.bundle": {"runs": 5, "blocks": 1}}
  },
  "report": {"path": "logs/policy/policy_audit_20251022-174512.json"}
}
```

## Logs & Provenance

- Enforcement logs append as JSONL under `logs/policy/enforcer.jsonl`. Each record stores the raw findings (`result.findings`) in addition to the level-normalised summary.
- Audit exports land in the same directory (`policy_audit_<timestamp>.json`), making it easy for compliance reviewers to archive checkpoints beside build artifacts.
- Import/export responses include `enforcement.result` so provenance sidecars (`provenance.json`) can embed the raw findings for downstream tooling.

## Modder Hooks

The modder hook bus gained `on_policy_enforced`:

- REST/WebSocket topic: `modder.on_policy_enforced`
- Payload:

  ```json
  {
    "event": "on_policy_enforced",
    "ts": 1732212345.12,
    "data": {
      "action": "import.vn",
      "allow": true,
      "counts": {"info": 0, "warn": 0, "block": 2},
      "blocked": [{"message": "License 'All Rights Reserved' forbids redistribution."}],
      "warnings": [],
      "log_path": "logs/policy/enforcer.jsonl"
    }
  }
  ```

Modders can subscribe via `GET /api/modder/hooks` (history) or open the WebSocket (`/api/modder/hooks/ws`) to mirror enforcement events in custom dashboards or automation scripts.

## Developer Notes

- Feature flag toggles live under **Settings → Debug & Feature Flags** once Studio refreshes the updated `feature_flags` map.
- `tests/test_policy_enforcer.py` covers log persistence, block behaviour, and audit exports; add new fixtures here when onboarding additional policy rules.
- When adding new import/export pipelines, call `policy_enforcer.enforce(<action>, bundle_payload)` before writing to disk so the JSONL timeline stays authoritative.
