# MASTER BACKLOG (Studio Edition)

> Use this as `docs/MASTER_BACKLOG.md`. Scope grows with the project; all items are modular and behind feature flags by default.

## 0) Global plumbing

* **Feature flags & drawers**: all new capabilities gated in Settings; externals OFF by default; Mini-VN ON.
* **DB/schema v0.6+**:
  `node.visible_to[]`, `node.narration{pov}`, `node.presentation{props,lights,lut}`,
  `character.anchors/traits/equipment/loras`, `worldline.events`, `battle.stats/outcome/beats`,
  `theme`, `weather`.
* **Provenance** everywhere: `{tool, version, workflow_hash, seed, worldline, pov, theme, weather}`.
* **Doctor**: one script that pings routes, checks flags, golden tests, log paths, and secrets safety.
* **Docs baseline**: README, Architecture, CHANGELOG; per-feature docs; modder hook registry.

---

## 1) Theme kits & Theme Swap Wizard

Theme kits ship **palettes/LUTs**, **SFX/music sets**, **overlay/prop bundles**, **camera defaults**, **prompt flavor**, and **asset-tag remaps** (e.g., `costume/school_uniform → costume/station_jumpsuit`).
Theme Swap: pick subtype (e.g., Horror → Gothic/Cosmic/Slasher), select **event anchors** to preserve, preview presentation plan, then **commit to VN Branch** worldline (OFFICIAL untouched).

**Starter (legal-clean) themes**

* Modern School • Urban Noir • Gothic Horror • Cosmic Horror • Cyberpunk • Space Station • Post-Apoc • High Fantasy • Historical Japan • Steampunk • Pirate High Seas • Superhero City • Mecha-Military • Cozy Slice-of-Life

Accessibility variants: high-contrast and color-blind friendly palettes.

---

## 2) Popular Visual Novels (presets; no IP assets)

Curated lists to inspire structure and default knobs (templates only, no franchise content):

* **General (SFW)**: *The House in Fata Morgana*, *Steins;Gate*, *Umineko no Naku Koro ni*, *Muv-Luv Alternative*, *Higurashi*, *Zero Escape/999*, *Danganronpa*, *Ace Attorney*, *VA-11 Hall-A*, *Clannad*. ([GitHub][1])
* **NSFW (gated branch)**: *Saya no Uta*, *Subarashiki Hibi*, (*Fate/stay night* had adult origins—use only as generic template patterns). ([GitHub][2])
* **“Contract Spirits”** (Fate-like, legal-clean default): Contractor/Spirit/Sigils, class affinities, duel anchors (reference remaster exists; we ship no IP). ([GitHub][3])

---

## 3) Mechanics (toggle per theme)

Branching + **Anchors** (always) • Affection/Trust/Rep • Sanity/Fear • Inventory/Loadout • Day Planner • Investigation mini-games • Stealth/Noise • **Battle** (editor overrides vs game sim) • **Adventure Mode (Text→Scene)**: structured plan JSON, runner-gated.

---

## 4) POV, Worldlines & Timeline overlay

* **Fork on confirm** → new **Worldline** (⭐ OFFICIAL / 🔵 VN Branch / ⚪ Scratch); delta-over-base edits.
* **Overlay timeline**: lanes with **thumbnails** (auto), **POV badges**, **diff badges** (add/remove/change), scrub/jump.
* **Auto-bio suggestions**: mine dated hints in sheets/lore (optional); dotted markers; “Apply all / Dismiss all”.
* **Depth-from-2D**: both **Auto** (3–6 planes) and **Manual masks** per scene; parallax in preview.

---

## 5) Playground 2.5D/3D → Snapshot→Node/Fork

* **Tier-0**: multi-plane parallax (cards + overlays) • orbit/pan; no heavy assets.
* **Tier-1**: **WebGL stage** (Qt WebEngine + Three.js) loads **glTF sets** + **VRM/glTF characters**; gizmos & light rig; fallback to billboards when 3D missing.
* **Snapshot** writes `render_config.json` (camera/FOV/transforms/lights/overlays/seeds) → “Add node” or “Fork”.

---

## 6) Flat image → layered sprite/background (characters + BG)

**Goal**: decompose single PNG/JPGs into cut-out character/props and parallaxable backgrounds. Semi-automatic with interactive touch-ups.

**Character cut-outs (foreground)**

* **rembg** (U²-Net) for quick matting; ComfyUI nodes exist. ([GitHub][4])
* **SAM / SAM2** for interactive masks (hair/clothes/hands). ([GitHub][5])
* **OpenPose / MediaPipe** for anchors (pose/face/hands). ([GitHub][6])
* Optional **Real-ESRGAN** for HD outline clean-ups. ([GitHub][7])

**Background decomposition**

* **MiDaS/ZoeDepth** → monocular depth → quantize to **planes** (3–6). ([PyTorch][8])
* **LaMa** inpainting to fill behind separated elements. ([GitHub][9])

**Pipelines to ship**

* `comfyvn/pipelines/flat2layers.py` → produces:
  `layered/character/{id}/{cutout,mask,anchors.json}` and `background/planes/{z}/plane.png`, plus sidecars.
* `tools/depth_planes.py` → interactive thresholds + parallax scale.

---

## 7) Asset extractors (on-demand installer + wrappers)

We fetch third-party tools on approval and call via shims (user must own rights; liability gate).

* **GARbro** (many VN archives). ([GitHub][10])
* **arc_unpacker** (broad JP engines; CLI). ([GitHub][1])
* **rpatool / unrpa** (Ren’Py `.rpa`). ([GitHub][11])
* **KrkrExtract / krkr-xp3** (KiriKiri XP3). ([GitHub][12])
* **AssetStudio** (Unity VNs). ([GitHub][13])
* **WolfDec / UberWolf** (Wolf RPG). ([GitHub][14])

**Scripts**

* `tools/install_third_party.py` (download to `third_party/` + shims + README).
* `tools/vn_extract.py` (engine detect → extract → `imports/<game>/raw_assets/` + license snapshot).
* `tools/doctor_extractors.py` (smoke: versions, formats, dry-run on samples).

---

## 8) Props (diverse, layered, HD-clean)

Anchors per pose: `face_forehead, cheek_l/r, left/right_hand, upper_torso, eyes, hairline, mouth, feet`.
Z-order enum: `under_bg, under_portrait, over_portrait, over_ui`.
Conditions grammar (`vars.stress > 0.6`, `weather == "rain"`).
Tweens: fade/drift/pulse/rotate/scale (clamped).
**Ensure-prop** via Visual Style Mapper; premultiplied alpha or SDF outlines; dedup + thumbnails.

---

## 9) Battle (Editor vs Game)

* **Editor**: always **Pick winner**; set `vars.battle_outcome`; optional seeded narration.
* **Game**: deterministic sim v0:
  `score = base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)`
  Show roll breakdown; POV changes voice, not outcome.

---

## 10) Narrator (heavy outliner) + VN Chat + LLM orchestration (opt-in)

Modes: **Observe → Propose → (Approve/Edit) → Apply → (optional Continue)** (default cap **3 turns**); Stop/Rollback ring buffer; **no auto-apply**, JSON schema enforced.
VN Chat works offline; SillyTavern bridge optional.
Role→Adapter→Device mapping: Narrator/MC/Antagonist/Extras can use different models/devices (multi-GPU) with budgets & sticky sessions (all OFF by default).

---

## 11) Viewer stack, Export, Goldens

Viewer priority: **Ren’Py native embed** → **Ren’Py Web** (webview) → **Mini-VN** fallback (always available).
Mini-VN produces timeline thumbnails (16:9).
Export (Ren’Py): POV & battle labels; optional **Bake** for weather/lighting; provenance bundle.
**Golden tests**: 3 sample scenes (linear / choice-heavy / battle) per POV; identical trace diffs across runs.

---

## 12) Dungeon API (grid or DOOM-lite)

Thin interface: `enter`, `step`, `encounter_start/resolve`, `leave` → returns snapshot hooks to mint VN nodes.
Backends: **grid crawler** (deterministic) or **WebGL stage** DOOM-lite (playground only). Outcomes map to **event anchors**.

---

## 13) Public providers (links + flags; no defaults)

Adapters expose `capabilities`, `pricing_url`, `last_checked`, and **dry-run**; UI shows links & timestamps (we never hardcode rates).

* **GPU/workflow**: RunPod, HF Inference Endpoints, Replicate, Modal. ([GitHub][10])
* **Image/Video**: Stability, fal.ai, Runway, Pika, Luma.
* **Translate/OCR/Speech**: DeepL, Google Translate, Google Vision, AWS Rekognition, Deepgram, AssemblyAI.
* **LLM**: OpenAI-compat, Anthropic-compat, Gemini, OpenRouter, Azure OpenAI.

---

## 14) Ops & ecosystem

Performance budgets (VRAM/CPU), lazy load/unload heavy assets; profiler marks & dashboard.
Opt-in telemetry (anonymized), crash reporter → diagnostics bundle.
Security: encrypted secrets (git-ignored), plugin sandbox (deny-by-default), WS topic allowlist; no secrets in logs.
Accessibility: high-contrast, scalable UI text, color-blind filters; controller mappings/hotkeys.
Marketplace: extension manifest schema + packaging + trust levels; install/uninstall; sandbox allowlist.
Cloud sync & backups: S3/GDrive manifest/delta; encrypted secrets; rotation.
Collab editing: CRDT + WS presence cursors/locks; converge under latency.

---

# 3-Phase Delivery Plan

> Each phase is shippable. Flags default OFF for externals; Mini-VN ON. Five coders (A–E) work in parallel; one auditor (F) does glue/verification.

## PHASE 1 — Core loop & ingestion (POV, overlay, extractors, flat→layers)

**Scope**

* POV fork-on-confirm → Worldlines (⭐/🔵/⚪) + Timeline overlay (thumbnails, POV badges, diff badges, scrub).
* Snapshot mode (Ctrl/⌘-K) → Add node / Fork.
* Depth-from-2D: Auto planes + Manual masks; Tier-0 parallax in Playground.
* Extractor installer + `vn_extract.py` wrapper; legal gate; `doctor_extractors.py`.
* Flat→Layers pipeline v1: rembg + SAM/SAM2 + MiDaS/ZoeDepth planes; LaMa optional inpaint; Real-ESRGAN optional upscaler. ([GitHub][4])
* Props v1 (anchors, z-order enum, conditions, tweens) + ensure-prop job.
* Theme kits v1 + Theme Swap Wizard (anchored).

**Acceptance**

* New lane appears on fork; snapshots deterministic; manual masks override auto.
* Extractors install on demand; dry-run works; legal log written. ([GitHub][10])
* Flat→layers produces cut-out + planes; Playground parallax smooth.
* Props attach/tween; theme swap restyles while anchors persist.

---

## PHASE 2 — Authoring brains (Narrator, Battle, Playground 3D, Viewer/Export)

**Scope**

* Narrator outliner (Observe→Propose→Approve→Apply→Continue) with 3-turn cap; Stop/Rollback; apply queue; VN Chat offline; prompt packs wired.
* Role→Adapter→Device mapping (multi-GPU optional), budgets & sticky sessions (flags OFF).
* Battle: **Editor Pick** + **Game sim v0** (formula + roll breakdown); POV voice only.
* Playground **Tier-1** WebGL stage (glTF/VRM) with gizmos & light rig; billboard fallback.
* Viewer stack priority (Ren’Py native→web→Mini-VN); Mini-VN thumbnailer.
* Export (Ren’Py): POV/battle labels; **Bake** toggle for weather/lighting; provenance.

**Acceptance**

* Narrator proposals are JSON-valid, never auto-apply; 3-turn cap enforced; rollback clean.
* Role mapping drawer shows dry-run routing; VN Chat works offline.
* Battle deterministic in Game; Editor override wins; narration flavor changes with POV.
* Stage loads glTF/VRM; snapshots deterministic; Viewer always shows one mode; export reproducible.

---

## PHASE 3 — World-scale (Dungeon API, public providers, ecosystem)

**Scope**

* Dungeon API (grid or DOOM-lite) → snapshot hooks to VN nodes.
* Public provider adapters surfaced with **pricing links** + timestamps; **dry-run** only by default (GPU/workflow, image/video, translate/OCR/speech, LLM).
* Remote installer: idempotent setup for ComfyUI / SillyTavern / LM Studio / Ollama; no clobbering configs.
* Marketplace (manifests, packaging, trust), Cloud sync/backups, Collab editing (CRDT), Perf dashboard, Observability (opt-in), Security hardening, Accessibility suite.

**Acceptance**

* Dungeon outcomes align to event anchors; snapshots mint VN nodes.
* Provider panels show health + pricing links (no rates hardcoded); nothing bills unless enabled.
* Remote installers write status and re-runs are no-ops.
* Auditor/Doctor green across Win/Linux fresh clones; docs fully synced.

---

## References (tooling)

* GARbro (VN archive browser). ([GitHub][10])
* arc_unpacker (CLI VN extractor). ([GitHub][1])
* rpatool / unrpa (Ren’Py RPA). ([GitHub][11])
* KrkrExtract / krkr-xp3 (KiriKiri XP3). ([GitHub][12])
* AssetStudio (Unity). ([GitHub][13])
* WolfDec / UberWolf (Wolf RPG). ([GitHub][14])
* rembg • SAM/SAM2 • MiDaS/ZoeDepth • LaMa • OpenPose • Real-ESRGAN. ([GitHub][4])
* VN lists & roundups (for SFW presets). ([GitHub][1])

---

If you want, I can paste this straight into a `docs/MASTER_BACKLOG.md` template plus drop **Phase 1/2/3 workboards** with acceptance checks so your five coders and the auditor can start immediately.

[1]: https://github.com/vn-tools/arc_unpacker?utm_source=chatgpt.com "vn-tools/arc_unpacker: CLI tool for extracting images and ..."
[2]: https://github.com/isl-org/ZoeDepth?utm_source=chatgpt.com "isl-org/ZoeDepth: Metric depth estimation from a single image"
[3]: https://github.com/ManicsteinerYX/GARbro-Mod?utm_source=chatgpt.com "ManicsteinerYX/GARbro-Mod: Visual Novels resource ..."
[4]: https://github.com/danielgatis/rembg?utm_source=chatgpt.com "Rembg is a tool to remove images background"
[5]: https://github.com/facebookresearch/segment-anything?utm_source=chatgpt.com "facebookresearch/segment-anything"
[6]: https://github.com/CMU-Perceptual-Computing-Lab/openpose?utm_source=chatgpt.com "CMU-Perceptual-Computing-Lab/openpose"
[7]: https://github.com/xinntao/Real-ESRGAN?utm_source=chatgpt.com "xinntao/Real-ESRGAN"
[8]: https://pytorch.org/hub/intelisl_midas_v2/?utm_source=chatgpt.com "MiDaS"
[9]: https://github.com/advimman/lama?utm_source=chatgpt.com "LaMa Image Inpainting, Resolution-robust Large Mask ..."
[10]: https://github.com/morkt/GARbro?utm_source=chatgpt.com "morkt/GARbro: Visual Novels resource browser"
[11]: https://github.com/shizmob/rpatool?utm_source=chatgpt.com "RPATools"
[12]: https://github.com/xmoezzz/KrkrExtract?utm_source=chatgpt.com "A tool that can extract and pack krkr2 and krkrz's xp3 files"
[13]: https://github.com/Perfare/AssetStudio?utm_source=chatgpt.com "AssetStudio is a tool for exploring, extracting and exporting ..."
[14]: https://github.com/Sinflower/WolfDec?utm_source=chatgpt.com "Sinflower/WolfDec: A Simple Wolf RPG File Decrypter"
