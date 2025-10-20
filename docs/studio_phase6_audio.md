ComfyVN — Studio Phase 6 (Audio & Music)
========================================

Scope
-----
Phase 6 establishes the audio subsystem for speech synthesis, adaptive music, and cache controls. The initial implementation focuses on API scaffolding and logging so downstream teams can swap in real engines without breaking contracts.

Subsystem Components
--------------------
- Core stubs in `comfyvn/core/audio_stub.py` generate deterministic artifacts and sidecars.
- API layer exposes `/api/tts/*` for synthesis and `/voice/*` for GUI voice management.
- Asset registry integrations store generated files under `exports/tts/` with JSON metadata.
- Future music remix endpoints will piggyback on the same logging and provenance patterns.

API Hooks
---------
`POST /api/tts/synthesize`
  - Request: `{text, voice?, scene_id?, character_id?, lang?, metadata?}`
  - Response: `{ok, artifact, sidecar, cached, voice, lang, info.metadata}`
  - Emits sidecar JSON for provenance hand-off to the asset registry.

`GET /voice/list`
  - Returns the voice profiles available via `comfyvn.core.memory_engine.Voices`.

`POST /voice/profile`
  - Persists profile settings and records `voice.profile` events for downstream analytics.

`POST /voice/speak`
  - Mirrors `synthesize` but keeps backwards compatibility with the GUI voice panel.

Data & Cache Flow
-----------------
1. Incoming synth requests funnel through `comfyvn/server/modules/tts_api.py`.
2. `synth_voice()` hashes `{voice|text|scene|character|lang}` to produce a deterministic filename.
3. If the artifact already exists, the stub returns `cached=True` and leaves the file untouched.
4. A JSON sidecar is written alongside each artifact describing inputs (`scene_id`, `character_id`, language).
5. Downstream asset registration can read both artifact and sidecar paths to populate `assets_registry`.

Logging & Debugging
-------------------
- Logger names: `comfyvn.api.tts`, `comfyvn.api.voice`, `comfyvn.audio.pipeline`.
- Default log file: `logs/server.log`; add a rotating handler for `logs/audio.log` if deeper tracing is needed.
- Debug checklist:
  1. `curl -X POST http://localhost:8000/api/tts/synthesize -d '{"text":"Line","voice":"neutral"}' -H 'Content-Type: application/json'`
  2. Inspect `exports/tts/<voice>_<hash>.txt` and `<voice>_<hash>.json` for matching metadata.
  3. Tail `logs/server.log` and confirm INFO lines show `cached=True` on the second request.
- Errors raise HTTP 400 for empty text and HTTP 500 for unexpected synthesis failures; both cases record WARN/ERROR entries in the log.

Future Hooks
------------
- Music remix endpoints should emit artifacts under `exports/music/` with the same sidecar contract.
- Integrate asset provenance by appending the sidecar payload to the `provenance` table once Phase 2 Part B completes.
- When swapping to a real TTS engine, preserve the `(artifact, sidecar, cached)` return signature to avoid breaking the GUI voice panel.
