# Studio Views Snapshot (2025-10-21)

## Scenes
- Dockable list (`ScenesPanel`) backed by `SceneRegistry`.
- Refreshes when File → New/Open/Recent project changes occur.
- Logging: `ScenesPanel` emits INFO when registry context shifts.

## Characters
- Dockable list (`CharactersPanel`) showing registry entries with origin metadata.
- Updates path automatically when project context changes.

## Import Processing
- Uses `/jobs/all` and `/vn/import/{id}` to show VN/roleplay job progress. The view was renamed from “Imports” to signal that it monitors every import job type, not just SillyTavern payloads.
- “Open Summary” button launches generated summary file when available.

## Audio
- Simple TTS front end hitting `/api/tts/synthesize`; tracks last artifact and opens it.
- Provides a starting point for the Phase 6 audio pipeline.

## Advisory
- Fetches `/api/advisory/logs` with resolved/unresolved filters.
- Designed to align with Phase 7 advisory scans.

All panels appear under Modules → … in the main menu and honour the project context restored via `QSettings`.
