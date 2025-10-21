# Audio Lab — 2025-10-21

## Overview
- Promote `/api/tts/speak` as the character-aware TTS entrypoint with cache keys derived from `(character, text, style, model)` and provenance sidecars carrying `seed/workflow/model`.
- Rework the music remix stub so `/api/music/remix` enqueues an `audio.music.remix` job, records artifact metadata, and answers with a `job_id`.
- Extend the Studio audio panel with character presets that auto-fill voice parameters and trigger the new TTS endpoint.

## References
- `comfyvn/server/modules/tts_api.py` — endpoint handler, cache plumbing, asset registration.
- `comfyvn/core/audio_stub.py` — synthesis adapter pushing seed/workflow/model metadata into sidecars.
- `comfyvn/server/modules/music_api.py` — remix stub job orchestration and response contract.
- `comfyvn/gui/panels/audio_panel.py` — GUI panel with character preset loader and speak shortcut.

## TTS Speak Endpoint
- **Schema & routing**: `POST /api/tts/speak` shares the `TTSRequest` model (now with optional `seed`) and keeps `/api/tts/synthesize` as an alias for legacy callers.
- **Cache identity**: `AudioCacheManager.make_key` is fed the character id, text hash, style, and model hash; cache hits short-circuit synthesis while returning the existing sidecar.
- **Sidecar provenance**: `audio_stub.synth_voice` stamps `seed`, `workflow`, and `model` into every sidecar (and cache metadata), regardless of ComfyUI or synthetic fallback.
- **Response payload**: `TTSResponse.info` now reports `seed`, `route`, and `asset_uid` (when registered) so Studio tooling can confirm provenance.

## Music Remix Stub
- **Job registration**: `/api/music/remix` calls `task_registry.register("audio.music.remix", …)` and updates the job to `running` before executing `music_remix.remix_track`.
- **Result storage**: upon success, the job metadata gains a `result` block with `artifact`/`sidecar`, status flips to `done`, and the API response mirrors the same pointers plus the `job_id`.
- **Failure path**: exceptions move the job to `error` status, log the stack, and surface a `500` with `music remix failed`.

## GUI Character Tester
- **Preset loader**: the audio panel instantiates `CharacterManager`, hydrates a combo-box of available presets, and shows a reload affordance.
- **Auto-fill behaviour**: selecting a character pushes voice/style/lang/model fields into the manual inputs and captures any declared `seed` for deterministic runs.
- **Speak actions**: both the manual `Speak` button and the new `Speak Character` shortcut POST to `/api/tts/speak`, including the preset seed when present, and surface route/seed/cache details in the status label.

## Acceptance
1. POST `/api/tts/speak` twice with the same `(character_id, text, style, model_hash)` — second call returns `cached=true` and identical artifact/sidecar; confirm sidecar JSON lists `seed`, `workflow`, `model`.
2. POST `/api/music/remix` — response carries `job_id`, `status="done"`, and artifact path; `jobs/status/{job_id}` reports the same artifact within `meta.result`.
3. Launch Studio → Audio panel, load a character preset, click **Speak Character**, and observe the status line include the resolved seed plus the `/api/tts/speak` route tag.
