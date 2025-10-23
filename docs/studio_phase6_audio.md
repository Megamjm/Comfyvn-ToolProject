ComfyVN — Studio Phase 6 (Audio & Music)
========================================

Scope
-----
Phase 6 establishes the audio subsystem for speech synthesis, adaptive music, and cache controls. The pipelines now delegate to ComfyUI workflows when available, while retaining deterministic local fallbacks so automated tests and offline work remain stable.

Subsystem Components
--------------------
- Core pipelines in `comfyvn/core/audio_stub.py` and `comfyvn/core/music_remix.py` drive ComfyUI workflows (TTS + MusicGen) when configured, with deterministic synthetic fallbacks if the server/workflows are unavailable.
- API layer exposes `/api/tts/*` for synthesis and `/voice/*` for GUI voice management.
- Asset registry integrations store generated files under `exports/tts/` with JSON metadata.
- Future music remix endpoints will piggyback on the same logging and provenance patterns.

API Hooks
---------
`POST /api/tts/speak`
  - Request: `{character?, text, style?, model?, seed?, lipsync?}`
  - Response: `{ok, data{path, sidecar, alignment[], alignment_path, lipsync_path?, cache_key}}`
  - Side effects: writes `alignment.json` and optional `lipsync.json` alongside the cached WAV under `data/audio/tts/<cache_key>/`.

`POST /api/tts/synthesize`
  - Request: `{text, voice?, scene_id?, character_id?, lang?, metadata?}`
  - Response: `{ok, artifact, sidecar, cached, voice, lang, style, info.metadata}`
  - Emits sidecar JSON for provenance hand-off to the asset registry.

`GET /voice/list`
  - Returns the voice profiles available via `comfyvn.core.memory_engine.Voices`.

`POST /voice/profile`
  - Persists profile settings and records `voice.profile` events for downstream analytics.

`POST /voice/speak`
  - Mirrors `synthesize` but keeps backwards compatibility with the GUI voice panel.

`POST /api/audio/mix`
  - Request: `{tracks:[{path, role?, gain?, gain_db?, offset?}], ducking?, sample_rate?, metadata?}`
  - Response: `{ok, data{path, sidecar, cache_key, duration, sample_rate, tracks[], ducking?, cached}}`
  - Deterministically caches mixes under `data/audio/mixes/<cache_key>/` so repeat calls reuse renders.

`POST /api/music/remix`
  - Request: `{scene_id, target_style, source_track?, seed?, mood_tags?[]}`
  - Response: `{ok, artifact, sidecar, info{scene_id,target_style,source_track,seed,mood_tags}}`
  - Stub writes deterministic remix artifacts under `exports/music/`.

Data & Cache Flow
-----------------
1. Incoming synth requests funnel through `comfyvn/server/modules/tts_api.py`.
2. `synth_voice()` hashes `{voice|text|scene|character|lang|style|model_hash}` to produce a deterministic filename and cache key.
3. When the active provider is `ComfyUI`, the workflow JSON (default: `workflows/tts_comfy.json`) receives templated inputs before being submitted to the running server. Generated audio is copied from the ComfyUI output directory into `exports/tts/`, preserving metadata in the sidecar.
4. If the workflow or server is missing, the synthetic fallback generates a WAV with the same cache key, ensuring repeatability.
5. The audio cache manager (`comfyvn/core/audio_cache.py`) checks `cache/audio_cache.json` to reuse prior renders.
5. JSON sidecars describe inputs (`scene_id`, `character_id`, language, style). Asset registration consumes artifact + sidecar.
6. Music remix requests follow the same artifact + sidecar pattern under `exports/music/`.
7. Alignment payloads are injected into the TTS sidecar, and when `lipsync=true` the frame-indexed lipsync JSON is stored and referenced for rig integration.
8. Mixer requests hash the normalized track list, ducking envelope, and sample rate to produce `data/audio/mixes/<cache_key>/mix.wav` plus a `mix.json` sidecar carrying render diagnostics.

Logging & Debugging
-------------------
- Logger names: `comfyvn.api.tts`, `comfyvn.api.voice`, `comfyvn.audio.pipeline`.
- Default log file: `system.log` in the user log directory; add a rotating handler for `audio.log` (same folder) if deeper tracing is needed.
- Debug checklist:
  1. `curl -X POST http://localhost:8000/api/tts/synthesize -d '{"text":"Line","voice":"neutral"}' -H 'Content-Type: application/json'`
2. Inspect `exports/tts/<voice>_<hash>.wav` and `<voice>_<hash>.json` for matching metadata. When ComfyUI is active, the sidecar includes `provider`, `source_file`, and `workflow` fields for traceability.
  3. Tail `system.log` in the user log directory and confirm INFO lines show `cached=True` on the second request.
  4. For cache inspection, view `cache/audio_cache.json` and confirm the `key` matches `{voice|text_hash|lang|character|style|model_hash}`.
  5. Test `/api/tts/speak` with `{"text":"Hello","character":"demo","lipsync":true}` and verify `alignment.json` + `lipsync.json` land beside the cached WAV under `data/audio/tts/<cache_key>/`.
  6. Test music remix with `curl -X POST http://localhost:8000/api/music/remix -H 'Content-Type: application/json' -d '{"scene_id":"scene.demo","target_style":"lofi","mood_tags":["calm"]}'` and check `exports/music/` for the rendered `.wav` plus sidecar. With ComfyUI enabled the sidecar will include `provider=comfyui_local` and a `source_file` pointing at the workflow output.
  7. Exercise `/api/audio/mix` using two local WAVs (`voice`, `bgm`) and confirm `mix.json` records the track gains, offsets, ducking envelope stats, and the cache key.

Audio Provider Settings
-----------------------
- The Settings panel now exposes dedicated sections for Text-to-Speech and Music Remix services.
- Open-source, freemium, and paid providers are listed with quick notes and portal links (Bark, Coqui XTTS, ElevenLabs, Azure Speech, Meta AudioCraft, Suno AI, Soundraw, AIVA, etc.).
- Selecting the ComfyUI option unlocks editable fields for the base URL, workflow JSON, and output directory so the studio can target local or remote ComfyUI hosts.
- Settings persist to `data/settings/config.json` (mirrored to the SQLite `settings` table) under the `audio.tts` and `audio.music` keys; the runtime reads these values to decide whether to call ComfyUI or fall back to the synthetic generator.
- Errors raise HTTP 400 for empty text and HTTP 500 for unexpected synthesis failures; both cases record WARN/ERROR entries in the log.

Future Hooks
------------
- Music remix endpoints should emit artifacts under `exports/music/` with the same sidecar contract.
- Integrate asset provenance by appending the sidecar payload to the `provenance` table once Phase 2 Part B completes.
- When swapping to a real TTS engine, preserve the `(artifact, sidecar, cached)` return signature to avoid breaking the GUI voice panel.
- For a ready-to-run ComfyUI pipeline, follow `docs/comfyui_music_workflow.md` to install `ComfyUI-Music-Gen` nodes and export a reusable workflow JSON.
