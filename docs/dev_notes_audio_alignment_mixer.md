ComfyVN Audio Dev Notes — Alignment & Mixer
===========================================

Context
-------
The stubbed audio lab now exposes deterministic hooks so contributors can script lip-sync previews, re-render mixes, or swap in custom DSP without rewriting core services. These notes summarize the available APIs, debug toggles, and modder-facing extension points.

Feature Flag
------------
All routes are guarded by `features.enable_audio_lab` (default **false**). Flip the flag in `config/comfyvn.json` or export `COMFYVN_ENABLE_AUDIO_LAB=1` before invoking the APIs; otherwise every request returns HTTP 403 so production builds stay dark.

Endpoints
---------
- `GET /api/tts/voices`
  - Returns the stub voice catalog (`id`, `name`, `character`, `lang`, `styles`, `default_model`, `tags`, `sample_text`).
- `POST /api/tts/speak`
  - Body: `{"character":"narrator","text":"Line","style":"neutral","model":"xtts","seed":123,"lipsync":{"enabled":true,"fps":60}}`
  - Returns `data` with `path`, `sidecar`, `cache_key`, `cached`, `checksum_sha1`, `text_sha1`, `alignment[]`, `alignment_checksum`, `alignment_path`, optional `lipsync_path`, and `lipsync` meta `{path,fps,frame_count}`.
- `POST /api/audio/align`
  - Body: `{"text":"Line","lipsync":true,"fps":30,"persist":true,"character":"narrator","style":"neutral","model":"xtts"}`
  - Returns alignment JSON plus `alignment_checksum`, `text_sha1`, optional lipsync payload, and persisted file paths when requested.
- `POST /api/audio/mix`
  - Body: `{"tracks":[{"path":"/abs/voice.wav","role":"voice","gain_db":0},{"path":"/abs/bgm.wav","role":"bgm","gain_db":-6}],"ducking":{"trigger_roles":["voice"],"amount_db":12},"sample_rate":44100}`
  - Serves cached renders from `data/audio/mixes/<cache_key>/mix.wav` while recording track metadata, waveform checksums, and render stats in `mix.json`.
- `POST /api/music/remix`
  - Stub remains available for queuing ComfyUI music runs or generating deterministic preview stems.

Filesystem Contracts
--------------------
- TTS cache root: `data/audio/tts/<cache_key>/`
  - `out.wav` — deterministic PCM waveform
  - `sidecar.json` — provenance (`inputs`, `checksum_sha1`, `bytes`, `alignment_checksum`, `text_sha1`, `voice_id`, cache state)
  - `alignment.json` — phoneme timings (`[{phoneme,t_start,t_end}]`)
  - `lipsync.json` / `lipsync_<fps>.json` — optional frame-by-frame payload with `fps` + `frames[]`
- Mix cache root: `data/audio/mixes/<cache_key>/`
  - `mix.wav` — summed output after ducking
  - `mix.json` — render diagnostics (`tracks`, `ducking`, `duration`, `sample_rate`, `checksum_sha1`, `bytes`, `peak_amplitude`, `rms`, `rendered_at`, `cache_key`, `cached`)
- Alignment cache root: `data/audio/alignments/<text_sha1>/`
  - `alignment.json` — persisted alignment payload when `/api/audio/align` is called with `persist`
  - `lipsync.json` / `lipsync_<fps>.json` — optional lipsync frames matching the requested fps

Debugging
---------
1. Set `LOG_LEVEL=DEBUG` (or `COMFYVN_LOG_LEVEL=DEBUG`) before launching the server to trace requests in `system.log` and observe cache hits/misses.
2. Use `curl` or `httpie` to post sample payloads; inspect sidecars directly to confirm metadata.
3. Delete a cache directory to force a re-render; compare successive `mix.json` payloads to confirm determinism.
4. Extend `tests/test_audio_routes_stub.py` when adding new fields so CI protects cache contracts.

Modding & Automation Hooks
--------------------------
- `on_audio_tts_cached` — emitted after `/api/tts/speak`; payload includes `cache_key`, `path`, `sidecar`, `character`, `style`, `model`, `voice_id`, `text_sha1`, `checksum_sha1`, `bytes`, `text_length`, `cached`, and `provenance`.
- `on_audio_alignment_generated` — emitted after `/api/tts/speak` and `/api/audio/align`; payload includes `alignment`, `alignment_path`, `lipsync_path`, `fps`, `alignment_checksum`, `text_sha1`, plus the submitted `character`, `style`, and `model` labels.
- `on_audio_mix_rendered` — emitted after `/api/audio/mix`; payload includes `cache_key`, `path`, `sidecar`, `duration`, `sample_rate`, `tracks`, `ducking`, `checksum_sha1`, `bytes`, `rendered_at`, and `cached`.

Subscribe through `/api/modder/hooks`, `POST /api/modder/hooks/test`, or `ws://<host>/api/modder/hooks/ws` (topics: `audio.tts.cached`, `audio.alignment.generated`, `audio.mix.rendered`). The payloads are tailored for dashboards, OBS overlays, or CLI batch tooling.

Modding Tips
------------
- **Custom lipsync processors**: Watch `alignment_path`, `alignment_checksum`, and `lipsync{path,fps}` in `/api/tts/speak` responses. Consume the JSON to drive Blender rigs, Live2D, or bespoke animation pipelines.
- **Realtime mixers**: `/api/audio/mix` accepts absolute paths, allowing mods to source stems from external tooling while retaining deterministic ducking and checksums.
- **Asset registry linkage**: Sidecars retain `cache_key`, `checksum_sha1`, and absolute paths; reuse them as provenance keys when registering assets or exporting bundles.
- **CLI batching**: Pre-compute `data/audio/mixes/` and `data/audio/alignments/` during nightly builds. The checker profile `p5_audio_lab` validates flag defaults, routes, and doc presence without enabling the flag in production.

Next Steps
----------
- Wire ComfyUI audio workflows to supply true phoneme timings while preserving the stub schema for backwards compatibility.
- Add GUI toggles so modders can download the generated `alignment.json`/`mix.json` directly from the Studio audio panel.
