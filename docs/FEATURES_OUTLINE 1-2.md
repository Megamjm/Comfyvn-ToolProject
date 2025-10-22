<!-- ComfyVN Architect | Phase 1/2  -->

# ComfyVN — Features Outline (Studio Edition)
_Last updated: 2025-10-21_

> One-page, hand-off friendly map of Studio scope. Use this as the common reference for new chats and PRs.

## 1) Core Platform

### 1.1 Studio Shell (multi-view UI)
**Intent:** Single app with dedicated views: Project Hub, Scenes, Characters, Timeline, Assets, Import Processing/Jobs, Compute, Audio, Advisory, Export, Logs.  
**Status:** In-Progress (GUI loads, menu duplication + metrics wiring outstanding).

### 1.2 Server Core (FastAPI + WS)
**Intent:** One `create_app()` factory; `/health`, `/status`, `/system/metrics` + WebSocket hub for jobs/events.  
**Status:** In-Progress (boot order fixed; endpoints stable; needs hardening & better GUI backoff).

### 1.3 SQLite Persistence (local-first)
**Intent:** Store scenes, characters, timelines, variables, assets, imports, jobs, providers, templates, translations, settings, provenance.  
**Status:** In-Progress (v0.6 tables to create/migrate; registry re-index required).

### 1.4 Config & Logging
**Intent:** Centralize logs to `./logs/` (`gui.log`, `server.log`, `launcher.log`); simple settings service for Studio.  
**Status:** In-Progress (mostly works; unify all paths).

## 2) Authoring & Runtime

### 2.1 Scenario Graph (Scene/Node/Choice/Action)
**Intent:** Canonical JSON schema for deterministic VN logic with conditions, actions, callbacks.  
**Status:** In-Progress (Canonical scene schema + deterministic runner live with `/api/scenario/{validate,run/step}`; authoring GUI + callbacks pending).

### 2.2 Variables & Flags (Scoped)
**Intent:** `global | session | scene` scopes; typed values; runtime API (get/set/list/reset).  
**Status:** Planned (endpoint stubs to build).

### 2.3 Choices & Seeded RNG
**Intent:** Conditional & weighted choices with reproducible playthroughs (seed).  
**Status:** In-Progress (ScenarioRuntime seeds + weighted choice picking implemented; UX wiring + branching analytics still queued).

### 2.4 Presentation Directives
**Intent:** Portrait/expression/pose/camera; tween transitions; timing & SFX cues.  
**Status:** Planned (hooks to add to renderer & GUI preview).

### 2.5 Save/Load & Checkpoints
**Intent:** Persist variables + node pointer + seed; exportable for test harness.  
**Status:** Planned.

## 3) Importers & Conversion

### 3.1 Roleplay Importer (TXT/JSON)
**Intent:** Convert chat logs into Scenes + Characters; preview & batch import.  
**Status:** In-Progress (multipart dep fixed; stabilize parsing & jobs).

### 3.2 VN Pack Importer (.pak/.zip/.rpa/.json)
**Intent:** Extract assets, scripts, metadata; map to ComfyVN scene graph; license tagging.  
**Status:** Planned (adapters to build; advisory flags on import).

### 3.3 Manga → VN Pipeline
**Intent:** Panel segmentation → OCR → bubble grouping → speaker inference → Scene synthesis; optional translation.  
**Status:** Planned (pipeline stubs + fix-up UI needed).

### 3.4 Template Remapper
**Intent:** Apply setting templates (Modern/Fantasy/Sci-Fi) to imported scenes (assets, LUTs, music sets).  
**Status:** Planned.

## 4) Asset Management & Provenance

### 4.1 Asset Registry + Sidecars
**Intent:** DB row + JSON sidecar per asset (hash, license, origin, tags) and thumbnail DB for fast browsing.  
**Status:** In-Progress (rebuild registry; implement sidecar policy & thumbs).

### 4.2 Provenance Stamping
**Intent:** Embed minimal metadata (tool/version/workflow hash/seed) into images/audio; DB ledger for lineage.  
**Status:** New (add on write/export).

### 4.3 Caching & Dedup
**Intent:** De-duplicate by hash; pin assets; prefetch & LRU policies.  
**Status:** Planned (policy layer to implement).

## 5) Compute & Rendering

### 5.1 System Metrics & Process Swapper
**Intent:** Display CPU/GPU/RAM charts; choose CPU vs GPU (local) at runtime.  
**Status:** In-Progress (API ready; GUI polling to wire; swapper UI to add).

### 5.2 Local/Remote GPU Offload
**Intent:** Device enumeration; job routing policy (auto/manual/sticky); remote provider registry (RunPod/Unraid/Custom).  
**Status:** Planned (GPU manager & `/api/gpu/*` stubs exist; provider adapters to add).

### 5.3 Compute Advisor
**Intent:** Recommend CPU/GPU/Remote based on job size & current load; user consent to offload.  
**Status:** New (advisor endpoint + policy rules to implement).

### 5.4 ComfyUI Integration
**Intent:** Image generation & node workflows; return assets with sidecars; LoRA usage per character.  
**Status:** In-Progress (playground API present; connector hardening to do).

## 6) Audio, TTS & Music

### 6.1 Character-Aware TTS
**Intent:** Synthesize voice lines with caching by (character, text, style, model); language = user’s locale.  
**Status:** Planned (TTS adapter + registry linkage).

### 6.2 Music Remix
**Intent:** Style-transform or loop/adapt music per scene; tie to advisory/legal constraints.  
**Status:** Planned (adapter stubs to add).

## 7) Advisory, Safety & Licensing

### 7.1 Liability Waiver & Policy Gates
**Intent:** Users must acknowledge responsibility before risky operations (NSFW/3rd-party assets).  
**Status:** New.

### 7.2 Advisory Scanner
**Intent:** License checks, SFW/NSFW flags, IP/rights heuristics; findings with fixes.  
**Status:** Planned (scans integrated into import/export).

### 7.3 SFW/NSFW Mode
**Intent:** Global toggle; server filters queries; export modes.  
**Status:** Planned.

## 8) Translation & Localization

### 8.1 Translation Manager
**Intent:** Batch translate imported text/manga to user language; confidence scoring; review queue.  
**Status:** Planned (translation table + UI tab).

### 8.2 Live Language Switch
**Intent:** Toggle language at runtime; fallback to original.  
**Status:** Planned.

## 9) Integrations & Adapters

### 9.1 SillyTavern Bridge
**Intent:** Sync extension; persona & world-lore import; health checks.  
**Status:** Missing (re-add `st_bridge/extension_sync.py` + installer guard).

### 9.2 Model Adapters (LLM, Local APIs)
**Intent:** Standard adapter interface: send(streaming?), cancel, metadata, retry policy.  
**Status:** Planned.

### 9.3 Remote Provider Catalog
**Intent:** Register providers; health check; credentials; custom endpoints (Unraid/K8s/Docker).  
**Status:** Planned.

## 10) Export & Packaging

### 10.1 Ren’Py Exporter
**Intent:** Build `.rpy` scripts + copy assets; minimal playable bundle; dry-run validation.  
**Status:** Planned (scaffold present; orchestrator to implement).

### 10.2 Studio Bundle Export
**Intent:** ZIP containing scenes, assets, `provenance.json`, README/license.  
**Status:** Planned.

## 11) Studio UX & Tooling

### 11.1 Scenes/Timeline Editors
**Intent:** Node editor with undo/redo; drag-drop timeline; preview runner.  
**Status:** Planned.

### 11.2 Import Processing/Jobs Dashboard
**Intent:** Background queue with WS updates; logs; retries; status filter.  
**Status:** In-Progress (jobs hub exists; UI to wire).

### 11.3 Diagnostics & Logs
**Intent:** Live console, error surfaces, health indicators; consistent logging paths.  
**Status:** In-Progress (normalize to `./logs/`).

### 11.4 Installer / Launcher
**Intent:** Windows-friendly: create venv, install deps, copy ST extension, prompt Ren’Py URL, press-to-launch GUI.  
**Status:** In-Progress (scripts exist; bridge missing; polish to complete).

## 12) Plugin / Extension Architecture (Future)

### 12.1 Plugin Loader
**Intent:** `/extensions/` folder with safe hook points (routes, events, UI injection).  
**Status:** Future.

---

## Suggested Phase Sequencing

**Phase 1: Core stabilization**  
Server boot order & `/health`; GUI ServerBridge stubs; metrics polling; logging path normalization.

**Phase 2: DB & Registry**  
Migrations for v0.6 tables; asset sidecars + thumbnails; rebuild registry from disk.

**Phase 3: Importers**  
Roleplay importer hardening → VN pack importer → Manga pipeline + fix-up UI.

**Phase 4: Studio Views**  
Scenes, Characters, Timeline, Assets, Import Processing; unify switching & inspectors.

**Phase 5: Compute**  
GPU manager + policy; remote provider registry; compute advisor; process swapper UI.

**Phase 6: Audio**  
TTS adapter + cache; music remix; studio audio lab.

**Phase 7: Advisory & Export**  
Liability gate; advisory scans; Ren’Py exporter; provenance manifest bundle.

---

### Notes on lag / carrying context
Long chats slow the session. Two options:
- Start a fresh chat titled **“ComfyVN Studio — Phase 1/2 Execution”**, paste this outline, and reference the repo.
- Keep this doc at `docs/FEATURES_OUTLINE.md` and have each new chat link to it.

_Integrations note:_ if present, keep `config/comfyvn.json` and any `sillytavern_extensions.js` in sync; LM Studio (OpenAI-compatible) typically at `http://localhost:1234`; ComfyUI default `http://127.0.0.1:8188`. Gate connectors behind flags during Phase 1.
