## ComfyVN Studio Phase 2 Notes

### Objectives

- Expand the Phase-06 rebuild to include all registry tables (variables, templates, providers, settings).
- Introduce foundational Studio registries (`comfyvn/studio/core`) to access the new schema rows.
- Prepare the ground for asset sidecar handling and provenance tracking.

### Deliverables (2025-10-20)

- `tools/apply_migrations.py` provisions:
  - `variables`, `templates`, `providers`, `settings` tables.
  - Supplemental directories (`comfyvn/data/settings`, `comfyvn/data/variables`).
  - Idempotent creation verified via `python tools/apply_migrations.py --dry-run` then `--verbose`.
- Studio registries (`comfyvn/studio/core`):
  - Added `TemplateRegistry` and `VariableRegistry` alongside existing Scene/Character/Asset/World registries.
  - Exposed via `comfyvn.studio.core.__all__`.

### Part B (Asset Registry & Sidecars) — 2025-10-21 Update

- Thumbnail generation runs inline during `register_file`; optional Pillow dependency still governs actual image output.
- Provenance hooks now write to the `provenance` table and stamp PNG metadata with a `comfyvn_provenance` marker when Pillow is available.
- Asset ingestion workflow documented in `docs/studio_assets.md` with CLI/SQLite debugging steps.
