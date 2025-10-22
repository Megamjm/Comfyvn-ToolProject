# Phase 8 Integration Report

Date: 2025-12-03 • Owner: Codex F (Auditor & Integrator)

## Scope & Outcomes
- **App factory hardening** — `comfyvn.server.app.create_app()` now records path/method signatures while loading routers, skipping legacy modules when they collide with the modern `/api/*` stack. `/health` and `/status` only register when missing, keeping downstream health checks deterministic.
- **Feature defaults synced** — `config/comfyvn.json` explicitly carries `enable_compute` (ON), `enable_mini_vn` + `enable_viewer_webmode` (ON), and the narrator/worldline/playground/depth/public-provider flags (OFF). The settings mirror documentation and the new doctor audit so CI catches drift early.
- **Doctor Phase 8** — Added `tools/doctor_phase8.py` to bootstrap `create_app()` headless, assert the battle/props/weather/viewer/narrator/modder/pov routes, ensure the modder hook catalogue exports the required events, verify WebSocket availability, and confirm feature defaults/security gitignore coverage. The script exits non-zero when any probe fails.
- **Documentation sweep** — README (doctor phase 8, flag guidance, compute toggle), `architecture.md` (router de-dupe notes), `CHANGELOG.md`, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and this report now reflect the current surface. Modders get updated endpoint + hook references and explicit instructions on running the doctor script.

## Verification
- `python tools/doctor_phase8.py --pretty`
- `pytest tests/test_playtest_headless.py tests/test_pov_worldlines.py`
- `pytest tests/test_battle_routes.py tests/test_props_routes.py tests/test_weather_routes.py`

All checks completed successfully; doctor output returned `"pass": true`.

## Follow-ups
- [ ] Monitor CI adoption of `tools/doctor_phase8.py` and add it to release checklists.
- [ ] Consider migrating legacy routers with empty prefixes to new `/api/*` namespaces or retire them once downstream clients have migrated.
- [ ] Keep feature flag tables in README / docs in sync when introducing new toggles so the doctor audit expectations stay accurate.
