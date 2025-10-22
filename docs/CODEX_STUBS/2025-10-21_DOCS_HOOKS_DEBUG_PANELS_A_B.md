# Docs, Hooks & Debug Panels — 2025-10-21

## Intent
- Refresh public-facing docs (README, ARCHITECTURE, CHANGELOG, CHANGEME) so modders can find the new Scenario Runner deck, POV service, and viewer endpoints without chasing chat logs.
- Land durable references (`docs/POV_DESIGN.md`, `docs/VIEWER_README.md`) for narrative POV logic, save-slot helpers, and Ren’Py viewer automation.
- Capture the debug/feature-flag toggle surface (hardened ComfyUI bridge) and Log Hub panel so contributors know where to inspect runtime state.

## Scope
- Studio timeline gets the Scenario Runner dock (live POV, seed, variables, breakpoints). Must document how it syncs with `/api/scenario/run/step` and `/api/pov/*`.
- Settings panel exposes `enable_comfy_bridge_hardening` — document how it persists to `config/comfyvn.json` and when to toggle it.
- Viewer control routes (`/api/viewer/start`, `/stop`, `/status`) should be discoverable with payload/env expectations and log paths.
- Update doc index so new artifacts live in the docs channel and CODEX ledger.

## Deliverables
- README highlights for Scenario Runner, Log Hub, viewer routes, and environment flags.
- ARCHITECTURE.md + architecture_updates.md entries tying TimelineView, POV manager, and viewer hooks into the phase plan.
- CHANGELOG + CHANGEME lines covering the doc sweep and new debug surfaces.
- New docs: `docs/POV_DESIGN.md`, `docs/VIEWER_README.md`.

## Acceptance
- Docs call out `/api/pov/{get,set,fork,candidates}` payloads, `/api/viewer/{start,stop,status}` behaviour, and the `enable_comfy_bridge_hardening` toggle.
- Contributors can follow the docs to tail logs (Panels → Log Hub) and launch the viewer without reading source.
- CODEX stub references landed work and cross-links to long-form docs.
