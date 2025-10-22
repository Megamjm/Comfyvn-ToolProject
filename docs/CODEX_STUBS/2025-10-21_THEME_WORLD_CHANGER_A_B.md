# Theme & World Changer — 2025-10-21

## Intent
- Surface author-facing theme presets that swap LUT stacks, ambient sets, music packs, and prompt styles for rapid world tone shifts (Modern, Fantasy, Romantic, Dark, Action).
- Let Studio queue world-template previews without issuing full renders: plan deltas should be deterministic so the GUI can diff/preview instantly.
- Support per-character spotlight overrides so leads can keep bespoke lighting or palette tweaks while bulk theme swaps adjust everyone else.

## Touchpoints
- Server API: `/api/themes/apply` builds checksum-stable plan deltas, merges optional scene state, and returns available templates for UI pickers.
- Theme Templates: `comfyvn/themes/templates.py` hosts orchestrated presets (assets + LUTs + music + prompt style + character defaults/roles) plus a `plan()` helper consumed by the API.
- Tests: `tests/test_theme_routes.py` covers deterministic planning, override handling, and route plumbing so regressions are caught alongside future template additions.

## Acceptance Hooks
- Posting `{"theme": "<name>", "scene": {...}}` returns `{ok: true, data: {plan_delta, templates}}`; `plan_delta.checksum` stays identical across identical payloads.
- Template application populates `mutations` for assets, LUTs, music, prompt, and character entries; each mutation block surfaces `before/after/changed`.
- Character overrides accept payloads under `overrides.characters.<character_id>` and bubble into the `plan_delta` list with deterministic ordering.

## Debug Notes
- Use `GET /api/themes/templates` to hydrate UI dropdowns or CLI tooling; response includes sorted template names and a count.
- When debugging plan shapshots, compare `plan_delta.mutations.*.before` against incoming scene state—anything missing indicates the scene never supplied that facet.
- Determinism relies on sorted dictionaries/lists before hashing; adding new template keys requires mirrored ordering to preserve checksum stability.
