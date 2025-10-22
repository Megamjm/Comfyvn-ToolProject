# ComfyVN Audio Lab — Character-aware TTS, Alignment, Mixer

The Audio Lab surfaces deterministic stubs for text-to-speech, phoneme alignment, and scene mixing so UI and automation layers can iterate without pulling in heavyweight DSP stacks. All routes are gated behind the feature flag `features.enable_audio_lab` (defaults to **false**).

## Flag & Routing Overview

- **Flag**: flip `features.enable_audio_lab` to `true` in `config/comfyvn.json` (or set `COMFYVN_ENABLE_AUDIO_LAB=1`) before hitting the APIs.
- **Routes** (all prefixed with `/api`):
  - `GET /tts/voices` — return the stub voice catalog (id, character, styles, default model).
  - `POST /tts/speak` — synthesize or reuse a cached clip keyed by `(character,text,style,model)`.
  - `POST /audio/align` — generate alignment JSON (optionally persist to disk and emit lipsync frames).
  - `POST /audio/mix` — mix stems with deterministic ducking and cache the result.
  - `POST /music/remix` — queue a placeholder remix job (metadata only, no DSP).

All endpoints short-circuit with HTTP 403 when the flag is off so smoke tests can assert that the lab stays dark in production builds.

## TTS Speak

```http
POST /api/tts/speak
{
  "character": "tester",
  "text": "Hello world preview",
  "style": "calm",
  "model": "stub",
  "seed": 123,
  "lipsync": {"enabled": true, "fps": 60}
}
```

- Cache key: SHA-1 of `(character|text|style|model)`; stored under `data/audio/tts/<cache_key>/`.
- Artifacts: `out.wav`, `sidecar.json`, `alignment.json`, optional `lipsync.json` (suffix includes fps when non-default).
- Response fields of note: `cached`, `checksum_sha1`, `text_sha1`, `alignment_checksum`, `lipsync_fps`, and `voice_id` when a stub catalog entry matches.
- Sidecar provenance: captures inputs (`character`, `style`, `model`, `seed`, `text`), `checksum_sha1`, `bytes`, `text_sha1`, `alignment_checksum`, and an optional lipsync meta block `{path,fps,frame_count}`.

## Alignment Service

```http
POST /api/audio/align
{
  "text": "Line for lipsync",
  "lipsync": true,
  "fps": 30,
  "persist": true,
  "character": "narrator",
  "style": "neutral",
  "model": "stub"
}
```

- Returns the phoneme list (`[{phoneme,t_start,t_end}]`) plus `alignment_checksum` and `text_sha1`.
- When `persist` is true the payload lands in `data/audio/alignments/<text_sha1>/alignment.json`; lipsync frames are written beside it (`lipsync.json` or `lipsync_<fps>.json`).
- Lipsync payload mirrors `alignment_to_lipsync_payload` (default `fps=60`, configurable per call).

## Mixer

```http
POST /api/audio/mix
{
  "tracks": [
    {"path": "/tmp/voice.wav", "role": "voice", "gain_db": 0, "offset": 0},
    {"path": "/tmp/bgm.wav", "role": "bgm", "gain_db": -6}
  ],
  "ducking": {"trigger_roles": ["voice"], "amount_db": 12},
  "sample_rate": 44100
}
```

- Cache key derived from absolute track paths, gain/offset, ducking config, and target sample rate.
- Mix render lives at `data/audio/mixes/<cache_key>/mix.wav` with metadata in `mix.json`.
- Sidecar fields: `tracks[]`, `ducking`, `sample_rate`, `duration`, `checksum_sha1`, `bytes`, `peak_amplitude`, `peak_db`, `rms`, `rms_db`, `rendered_at`, and `cached`.
- Repeated requests reuse the same WAV without recomputing the buffer; checksums allow diffing downstream effects.

## Voice Catalog

`GET /api/tts/voices` surfaces the stub catalog used by the UI. Each entry includes `id`, `name`, `character`, `lang`, `styles`, `default_model`, `tags`, `description`, and a short `sample_text`. Use these ids as hints when seeding project-specific defaults or presenting dropdowns.

## Modder Hooks

Events are emitted through the central modder hook bus for automation dashboards, OBS overlays, or CLI batching:

- `on_audio_tts_cached` — fires after `/tts/speak`, includes cache key, character/style/model, checksum, and provenance.
- `on_audio_alignment_generated` — fires after `/tts/speak` and `/audio/align`, includes `alignment`, `alignment_checksum`, optional lipsync path, and context labels.
- `on_audio_mix_rendered` — fires after `/audio/mix`, includes mix metadata, checksum, byte size, and cache state.

Inspect them via `GET /api/modder/hooks` or subscribe to `ws://<host>/api/modder/hooks/ws` with the topics `audio.tts.cached`, `audio.alignment.generated`, `audio.mix.rendered`.

## Debugging Checklist

1. Set `LOG_LEVEL=DEBUG` to trace cache hits, alignment writes, and mix renders in `logs/server.log`.
2. Use the checker profile `python tools/check_current_system.py --profile p5_audio_lab --base http://127.0.0.1:8001` to validate flag defaults, routes, and doc coverage.
3. Remove cache directories under `data/audio/{tts,mixes,alignments}` to force regeneration when testing determinism.
4. `pytest tests/test_audio_routes_stub.py -k audio` exercises the stub routes, ensuring cached responses stay stable.

## File Layout Summary

```
data/
  audio/
    tts/<cache_key>/
      out.wav
      sidecar.json
      alignment.json
      lipsync.json | lipsync_<fps>.json
    mixes/<cache_key>/
      mix.wav
      mix.json
    alignments/<text_sha1>/
      alignment.json
      lipsync.json | lipsync_<fps>.json
```

Keep these directories under version control ignore lists; they are generated artifacts meant for local inspection and export bundles, not source history.
