# Phase 6 — POV & Center Viewer

## Tracks (A/B)
1. POV Core & Runner — A manager + REST, B runner filters/forks
2. VN Viewer — A default center, B Ren'Py embed/fallback
3. Character Designer — A CRUD, B Comfy render + registry
4. Chat/Narrator — A chat panel, B narrator drives scenes
5. LLM Registry/Adapters — A registry, B adapters + proxy
6. ST Compat/Session — A health/sync, B context push/pull
7. POV Render/LoRA — A ensure missing renders, B LoRA-aware cache
8. View Router/Flags — A center router, B persisted flags
9. Export POV Forks — A branch labels, B master multi-fork
10. Docs/Hooks/Debug — A docs, B Debug panel

**DoD (global)**
- Viewer is default center; shows “waiting for project” when idle.
- POV switch changes available choices; forked saves diverge.
- Chat panel works offline (adapter stub) and with ST when enabled.
- No file overlaps across A/B tracks; flags default OFF for external services.
