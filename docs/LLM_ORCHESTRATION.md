# LLM Role Orchestration

## Goals
- Map narrative roles (Narrator, MC, Antagonist, Extras) onto adapters/models/devices.
- Track token budgets, sticky sessions, and health without requiring external services.
- Provide deterministic offline fallback when no adapter is configured.

## Feature Flag
- `enable_llm_role_mapping` (default: OFF). All `/api/llm/(roles|assign|health)` endpoints enforce the flag; pass `force: true` for local dry runs.

## Default Behaviour
- All roles start **disabled** (`adapter = None`, `status = "disabled"`).
- Offline adapter (`offline.local`, model `codex/offline-narrator`) is always available for dry runs and narrator chat.
- Sticky sessions only activate when both `sticky=true` and a non-offline adapter is present.

## Session & Budget Model
- Every assignment stores:
  - `adapter`, `model`, `device`
  - `budget`: tokens `limit`, `spent`, and `remaining`
  - `sticky`: boolean; when true a stable `session_id` is minted.
- Live sessions are recorded under `sessions[]` with message counts and token usage.
- Budgets are optimistic: dry runs never mutate `spent`; live routes reject when `would_remaining < 0`.

## Offline Adapter
- Deterministic reply generator, keyed by `(role, message, context digest)`.
- Metadata:
  ```json
  {
    "id": "offline.local",
    "label": "Offline Codex Narrator",
    "model": "codex/offline-narrator",
    "device": "cpu",
    "capabilities": {"chat": true, "offline": true, "deterministic": true}
  }
  ```
- Used automatically when a role is disabled or an assignment exhausts budget.

## API Reference (`/api/llm/*`)
- `GET /roles?dry_run=true&role=Narrator&message=Plan`  
  - Returns snapshot of assignments.  
  - With `dry_run=true`, includes `plans[]` (one per requested role) summarising adapter/model/device, estimated tokens, and budget impact.
- `POST /assign`
  ```json
  {
    "role": "Narrator",
    "adapter": "openai.gpt",
    "model": "gpt-4.1-mini",
    "device": "api",
    "budget_tokens": 18000,
    "sticky": true,
    "metadata": {"region": "us-east"}
  }
  ```
  - Passing `"adapter": null` or `"adapter": "off"` resets the role to offline mode.
- `GET /health`
  - Returns `{"ok": true, "roles": [...], "sessions": [...], "offline": {...}}`.

## Dry-Run Routing
- Utilise `GET /api/llm/roles?dry_run=true` when building UI previews or tests.
- Planner output example:
  ```json
  {
    "role": "Narrator",
    "adapter": "offline.local",
    "model": "codex/offline-narrator",
    "device": "cpu",
    "assigned": false,
    "plan_tokens": 44,
    "budget": {
      "limit": 0,
      "spent": 0,
      "remaining": 0,
      "would_spend": 44,
      "would_remaining": 0,
      "permitted": true
    },
    "session": null,
    "context": {"roster":"MC","summary":"...","digest":"7ea891aa"}
  }
  ```

## Debugging Checklist
- ✅ `/api/llm/roles` returns offline snapshot when feature disabled (403 otherwise).
- ✅ `/api/llm/roles?dry_run=true` surfaces planner output for every enabled role.
- ✅ `/api/llm/assign` toggles sticky sessions and budgets deterministically.
- ✅ `/api/llm/health` lists live sessions (including offline fallback `offline:<role>` identifiers).
- Budgets are clamped to non-negative integers; overspend attempts mark assignments as `"status": "exhausted"`.
- CI helpers: `python tools/check_current_system.py --profile p2_narrator --base http://127.0.0.1:8001` validates that both `enable_llm_role_mapping` flag defaults remain off, role routes respond, and documentation is present.

## Safety Notes
- Offline fallback ensures no accidental API calls when the feature flag remains OFF.
- Hooks and status payloads do not surface secrets; adapters may only include pricing links, never rates.
- Session registry is in-memory. Restarting the process resets assignments and budgets.
