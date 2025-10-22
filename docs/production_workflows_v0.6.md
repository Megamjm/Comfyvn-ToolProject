# ComfyVN Production Workflows (v0.6)

This document captures the “Consistency-First” production wiring for sprites, scenes, video, and voice. It supplements `ARCHITECTURE.md` by mapping data contracts (`character.json`, `scene.json`, `voice_clip.json`) to the canonical ComfyUI graphs, provider pins, and bridge modules added in this update.

## 1. Guiding Principles

- **Determinism** – record seeds, sampler, model hash, and node commit for every render. Workflows expect seeds in the `RenderContext.seeds` map and write sidecars (`*.render.json`, atlas manifests) for reproducibility.
- **Identity lock** – characters use IPAdapter FaceID/Style; ControlNet anchors structure; Impact detailers run last.
- **Single source of truth** – pipelines read from `data/characters/<id>/character.json` (legacy flat files mirrored for compatibility), `data/scenes/*.json`, `data/voices/*.json`. Exporters (Ren’Py, VN bundle, web gallery) consume the same JSON.
- **Batching** – sprite/shot lists run as arrays; video and TTS support chunking and resume.
- **Re-renderable** – PNG sidecars + JSON prompt logs; audio exports include SRT/VTT with timestamps.

## 2. Bridge Layer

| Module | Purpose |
| --- | --- |
| `comfyvn/bridge/comfy.py` | Async REST client for ComfyUI queue/history/artifact download. Wraps submission retries, metadata logging, and download helpers. |
| `comfyvn/bridge/tts.py` | TTS bridge around `ComfyUIAudioRunner` with XTTS → optional RVC conversion and loudness normalization. |
| `comfyvn/bridge/remote.py` | SSH-based remote compute helper (capability probe, push/pull, command execution). |
| `comfyvn/core/comfy_bridge.py` | Thread-safe wrapper exposing sync + async helpers for FastAPI modules (`/comfyui/*`). |

`RenderContext` aligns with the production JSON contracts, ensuring seeds, packs, pins, and tags persist through queue submissions.

## 3. Provider Registry

- Canonical template: `comfyvn/providers/providers.json` (node packs + model hints).
- Lock file: `comfyvn/providers/nodeset.lock.json` (pinned commits; update via `tools/lock_nodes.py`).
- `tools/lock_nodes.py` scans local `custom_nodes/` / `extensions/` checkouts, captures `git rev-parse HEAD`, and rewrites the lock.

Consumers (GUI, doctor scripts) should prefer the template to seed user-space registries before applying overrides.

## 4. Workflow Families

| Workflow | Description | Seed Keys | Notes |
| --- | --- | --- | --- |
| `comfyvn/workflows/sprite_pack.json` | Identity-locked sprite batch (OpenPose ControlNet + SpriteSheetMaker). | `character_seed`, `detail_seed`, `control_seed` | Emits per-pose PNGs plus atlas PNG/JSON. |
| `comfyvn/workflows/scene_still.json` | SDXL background + FLUX hero fusion with SAM2 compositing. | `background_seed`, `hero_seed` | Writes render log sidecar for provenance. |
| `comfyvn/workflows/video_ad_evolved.json` | AnimateDiff Evolved with Advanced-ControlNet scheduling, Impact detailers, RIFE interpolation, VHS mux. | `animation_seed`, `detail_seed`, `rife_seed` | Accepts timeline prompt schedule + pose sequence arrays. |
| `comfyvn/workflows/voice_clip_xtts.json` | XTTS synthesis with limiter/de-esser, optional RVC mix, subtitle export. | `tts_seed` | Produces WAV + SRT and `.render` metadata. |

Each JSON includes metadata (`family`, `version`, `packs`, `expected_inputs`) so the GUI and CLI can provide assistant forms and validations.

## 5. Data Contracts

The production workflows assume the JSON shapes defined in the long-term plan:

- `character.json` – seeds per pose family, IPAdapter references, ControlNet defaults, voice preferences.
- `scene.json` – background prompt/style + seed, character placements, shot list (stills/video), and dialogue lines tied to `voice_clip` IDs.
- `voice_clip.json` – text, speaker, engine preference, reference audio, timing target, optional RVC post.

## 6. Implementation Tasks (Tracking)

- [x] Bridge modules (`comfy.py`, `tts.py`, `remote.py`) with retry, logging, and download helpers.
- [x] Provider template + lock and `lock_nodes.py` helper.
- [x] Canonical ComfyUI JSON graphs for sprite, scene, video, voice workflows.
- [ ] Exporters for Ren’Py / VN bundle / web gallery (pending Phase 7/8 tasks).
- [ ] GUI wiring for Sprite Manager, Voice Manager, Scene Board, Video Render (Phase 6+).
- [ ] Remote compute profiles and sync orchestrators (Phase 5 follow-up).

## 7. Usage Notes

1. **Queueing** – Use `ComfyBridge.submit_async({...})` with `workflow_id`, `inputs`, `packs`, `pins`, `seeds`, and either an in-memory workflow (`dict`) or path to the JSON template. The bridge logs node packs/tags in `extra_data.comfyvn`.
2. **Artifacts** – `RenderResult.artifacts` captures filenames, node IDs, and metadata (seed, resolution). Call `download_artifacts(result, Path)` to copy to project storage.
3. **Voice** – `TTSBridge.synthesize_clip()` infers engine fallback order from clip metadata and canonical `preferred_tts` lists. Loudness normalization targets −16 LUFS / −1 dBTP.
4. **Remote** – `RemoteBridge.capability_probe()` executes `nvidia-smi`, `ffmpeg -version`, and a `torch.cuda` check. Extend the command list for provider-specific diagnostics.
5. **Roleplay pipeline** – `/roleplay/import` now persists `raw/`, `processed/`, and `final/` transcripts. Editors can call `/roleplay/apply_corrections` and `/roleplay/sample_llm` with detail levels (`low|medium|high`) to coordinate LLM-driven cohesion passes.
6. **SillyTavern bridge** – Configure the base URL + plugin path via **Settings → Integrations**. The browser extension mirrors the same values (stored in `localStorage`) so world/character/persona downloads stay rooted to their original directories.

## 8. Export Targets

- **Ren’Py** – expects sprite atlases + manifest JSON, voice WAV/OGG with SRT, render logs per scene.
- **VN Bundle** – structure: `bundle/<scene_id>/{images/, audio/, sprites/, scene.json, manifest.json, versions.json}`.
- **Web Gallery** – `index.html` + `assets/` with atlases, mapping JSON, audio.

Exporter work remains tracked under Phase 8 (Export/Packaging).

---

For deviations or additional node packs, update `providers.json` and regenerate the lock. Keep sidecar manifests (`*.render.json`, atlas `.json`) in Git when they serve as golden references; user-generated artifacts stay in runtime data directories per `README.md`.
