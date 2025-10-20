## ComfyVN Studio Phase 2 Notes

### Objectives

- Expand the Phase-06 rebuild to include all registry tables (variables, templates, providers, settings).
- Introduce foundational Studio registries (`comfyvn/studio/core`) to access the new schema rows.
- Prepare the ground for asset sidecar handling and provenance tracking.

### Deliverables (2025-10-20)

- `tools/apply_phase06_rebuild.py` now provisions:
  - `variables`, `templates`, `providers`, `settings` tables.
  - Supplemental directories (`comfyvn/data/settings`, `comfyvn/data/variables`).
  - Idempotent creation verified via `python tools/apply_phase06_rebuild.py --recreate-all`.
- Studio registries (`comfyvn/studio/core`):
  - Added `TemplateRegistry` and `VariableRegistry` alongside existing Scene/Character/Asset/World registries.
  - Exposed via `comfyvn.studio.core.__all__`.

### Pending for Part B (Asset Registry & Sidecars)

- Implement thumbnail worker and asset sidecar generation.
- Wire provenance hooks to the registry entries.
- Document asset ingestion workflow once implemented.
