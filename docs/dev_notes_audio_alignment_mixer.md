ComfyVN Audio Dev Notes — Alignment & Mixer
===========================================

Context
-------
The stubbed audio lab now exposes deterministic hooks so contributors can script lip-sync previews, re-render mixes, or swap in custom DSP without rewriting core services. These notes summarize the available APIs, debug toggles, and modder-facing extension points.

Endpoints
---------
- `POST /api/tts/speak`
  - Body: `{"character":"narrator","text":"Line","style":"neutral","model":"xtts","seed":123,"lipsync":true}`
  - Returns `data` with `path`, `sidecar`, `alignment[]`, `alignment_path`, optional `lipsync_path`, and `cache_key`.
  - Sidecar payload gains `alignment` and `lipsync` entries so mods can ingest timing without scanning the filesystem.
- `POST /api/audio/mix`
  - Body: `{"tracks":[{"path":"/abs/voice.wav","role":"voice","gain_db":0},{"path":"/abs/bgm.wav","role":"bgm","gain_db":-6}],"ducking":{"trigger_roles":["voice"],"amount_db":12},"sample_rate":44100}`
  - Serves cached renders from `data/audio/mixes/<cache_key>/mix.wav` and logs track metadata in `mix.json`.
- `POST /api/music/remix`
  - Stub remains available for queuing ComfyUI music runs or generating deterministic preview stems.

Filesystem Contracts
--------------------
- TTS cache root: `data/audio/tts/<cache_key>/`
  - `out.wav` — deterministic PCM waveform
  - `sidecar.json` — provenance + alignment metadata
  - `alignment.json` — phoneme timings (`[{phoneme,t_start,t_end}]`)
  - `lipsync.json` — optional frame-by-frame payload with `fps` + `frames[]`
- Mix cache root: `data/audio/mixes/<cache_key>/`
  - `mix.wav` — summed output after ducking
  - `mix.json` — render diagnostics (`tracks`, `ducking`, `duration`, `sample_rate`, `cache_key`)

Debugging
---------
1. Set `LOG_LEVEL=DEBUG` (or `COMFYVN_LOG_LEVEL=DEBUG`) before launching the server to trace requests in `system.log` and observe cache hits/misses.
2. Use `curl` or `httpie` to post sample payloads; inspect sidecars directly to confirm metadata.
3. Delete a cache directory to force a re-render; compare successive `mix.json` payloads to confirm determinism.
4. Extend `tests/test_audio_routes_stub.py` when adding new fields so CI protects cache contracts.

Modding & Automation Hooks
--------------------------
- **Custom lipsync processors**: Watch the `alignment_path` or `lipsync_path` fields returned by `/api/tts/speak`. Consume the JSON in extensions to drive Blender rigs, Live2D, or on-the-fly animation.
- **Realtime mixers**: The mix endpoint intentionally accepts absolute paths, so mods can generate stems elsewhere and still leverage deterministic ducking plus caching.
- **Asset registry linkage**: Sidecars retain `cache_key` and absolute paths; use these as keys when registering new assets or writing export scripts.
- **CLI batching**: Scripts can pre-populate `data/audio/mixes/` by iterating dialogue JSON and posting to `/api/audio/mix`; the cache prevents duplicates while keeping metadata coherent.

Next Steps
----------
- Wire ComfyUI audio workflows to supply true phoneme timings while preserving the stub schema for backwards compatibility.
- Add GUI toggles so modders can download the generated `alignment.json`/`mix.json` directly from the Studio audio panel.
