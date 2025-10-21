# CHAT_WORK_ORDERS — Studio v0.7 Release

Updated: 2025-10-26 • Owner: Project Integration & Docs (Chat P)

## Release scope
- Target tag: `v0.7.0-studio` no later than 2025-10-27.
- Ship unified Studio shell (Scenes, Characters, Timeline) backed by stable registries and provenance-aware imports.
- Ensure compute/advisory/audio subsystems surface telemetry and provenance required for packaging + compliance docs.
- Lock documentation set: `ARCHITECTURE.md`, `README.md`, `docs/UPGRADE_v0.7.md`, `docs/packaging_plan.md`, and `docs/production_workflows_v0.7.md` (rename from v0.6).

## Work orders (P0 blockers — must land before tag)
- ⚠ **Asset inspector UX** (Asset & Sprite System Chat) — Build Studio assets panel inspector (thumbnails, provenance drill-down, open-in-finder, delete/register hooks). Depends on registry + advisory metadata contract.
- ⚠ **Audio ComfyUI linkage** (Audio & Policy Chat) — Wire `/api/tts/*` and `/api/music/remix` to push provenance + sidecars into `AssetRegistry`; expose job telemetry so GUI shows progress + cache state.
- ⚠ **Manga importer parity** (Importer Chat) — Deliver segmentation → Scene synthesis parity with VN importer, register assets/logs, and surface preview in Studio import dashboard. Coordinate advisory scan hooks.

## Work orders (P1 support — close before announcement)
- ✅ **Remote compute validation** (Remote Compute Chat) — Run smoke across RunPod/Vast/Vast-like providers; ensure `/jobs/ws` telemetry + retry policy documented.
- ⚠ **Export orchestrator dry-run** (Export/Packaging Chat) — Run Ren’Py bundle dry-run with current registries; capture gaps for Phase 9 backlog notes in `ARCHITECTURE.md`.
- ⚠ **Advisory auto-remediation hooks** (Advisory/Policy Chat) — Emit structured events for replace/remove/waiver actions; feed GUI toast/log. Not a hard blocker but release note must call out limitation if it slips.
- ✅ **Runtime storage parity check** (System/Server Core Chat) — Confirm symlinks + platformdirs paths working on Win/macOS/Linux; update troubleshooting appendix if new quirks found.

## Documentation & comms
- ⚠ Refresh `README.md` overview + feature list for Studio v0.7 (highlight Studio shell, importers, advisory/audio systems).
- ⚠ Expand `docs/UPGRADE_v0.7.md` with migration steps (runtime storage, doctor script, registry rebuild guidance).
- ⚠ Rename/extend `docs/production_workflows_v0.6.md` → `docs/production_workflows_v0.7.md`; ensure ComfyUI workflow references match shipped templates.
- ✅ Coordinate CHANGELOG + docs/CHANGEME updates with release highlights and outstanding caveats.
- ✅ Update `docs/packaging_plan.md` + `docs/extensions.md` references if asset inspector or audio flows alter packaging requirements.

## QA & release checklist
- ✅ Smoke: `run_comfyvn.py --server-only` + `/health`/`/status` probe.
- ⚠ GUI regression sweep covering Scenes/Characters/Timeline + new assets inspector once it lands.
- ⚠ Import regression: roleplay + VN + manga (new flow) + advisory + provenance checks.
- ⚠ Audio regression: cached + uncached TTS, music remix, provenance sidecars present.
- ⚠ Verify remote GPU job submission (auto/manual/sticky) with telemetry + fallback.
- ✅ Doctor script (`tools/doctor_v07.py`) updated and documented for release note.
- ⚠ Tag & packaging rehearsal (wheel + PyInstaller/AppImage) once blockers land; capture artefacts under `exports/builds/`.
