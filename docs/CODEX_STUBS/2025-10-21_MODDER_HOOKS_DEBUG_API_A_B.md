# Modder Hooks, Debug API & Integrations Panel — 2025-10-21

## Intent
- Consolidate modder-facing events behind a single hook bus with durable REST/WebSocket surfaces so contributors can automate against scene, choice, and asset updates.
- Provide a first-class Studio diagnostics view for compute providers (health, quotas, masked credentials) to keep API onboarding out of terminal-only scripts.
- Refresh the documentation spine (README → architecture → changelog → dev notes) and ledger entries so the docs channel stays aligned with the new surfaces.

## Scope
- Core hook bus (`comfyvn/core/modder_hooks.py`) exposing `on_scene_enter`, `on_choice_render`, `on_asset_saved` with plugin host, history, and listener registration.
- Emitters: Scenario Runner (initial state + step), AssetRegistry registration callbacks, webhook forwarder, hook REST/WS routes under `/api/modder/hooks/*`.
- Studio panel: `comfyvn/gui/panels/debug_integrations.py` wired into the System workspace + menu; polls `/api/providers/health` and `/api/providers/quota` with masked config display and auto-refresh controls.
- Docs sweep: README, ARCHITECTURE.md, architecture_updates.md, CHANGELOG.md, docs/CHANGEME.md, dev notes (`docs/dev_notes_modder_hooks.md`, `docs/development/observability_debug.md`).

## Deliverables
- Hook bus module, FastAPI routes, and listener registration tests or smoke coverage.
- Scenario + asset emitters with timestamped payloads and webhook bridge registration.
- Debug Integrations panel + menu wiring; ensure System workspace opens the dock automatically.
- Documentation updates + codex stub entry capturing the work order.

## Acceptance
- Example plugin in `dev/modder_hooks/` receives `on_scene_enter` in dev mode (manual smoke check acceptable).
- `GET /api/modder/hooks` lists hooks with payload descriptions; WebSocket stream surfaces live envelopes while scenarios run.
- Debug Integrations panel renders provider statuses (green/amber/red) and shows quota fields for providers that support them; credential fields remain masked.
- README/architecture/changelog/CHANGEME/dev notes mention the new hooks, panel, and endpoints; codex ledger records the work order.
