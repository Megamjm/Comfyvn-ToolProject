ComfyVN Project Roadmap — Version 0.3
Phase 3: Feature Expansion and Creative Systems

Overview:
Version 0.3 focuses on adding interactivity, immersion, and automation to the ComfyVN ToolProject.
The goal is to transform the current baseline into a creative suite capable of live editing, adaptive presentation, and world-aware rendering while maintaining full modular separation between systems.

───────────────────────────────
Subsystem: GUI
Priority: Immediate
Features:
• Scene Flow Graph Editor — Node-based story visualizer with drag-and-drop route creation.
• Live Render Preview — Embedded window displaying current scene composite.
• Asset Drag-and-Drop Registration — Drop files or LoRAs directly into the GUI.
• Performance Overlay — Realtime resource monitor with mode auto-adjust.
• Narrative Timeline — Horizontal bar showing branching and progression.
Status: Planned

───────────────────────────────
Subsystem: Server Core
Priority: Immediate
Features:
• Batch Chat Importer — Automatic conversion of SillyTavern logs to scene JSONs.
• Smart Scene Builder — Auto-detect emotion and context to suggest composition.
• Auto Scene Diff Tool — Highlights JSON changes between revisions.
• Render Queue Prioritization — Adjustable job importance system.
• Extension Hooks — Allow third-party scripts to register server endpoints.
Status: Planned

───────────────────────────────
Subsystem: World Lore
Priority: Immediate
Features:
• Lore-based Lighting Profiles — Automatic time-of-day and color tone.
• Dynamic Weather States — Rain, fog, snow, and wind determined by lore or emotion.
• Culture Rulesets — Regional art, clothing, and architecture defaults.
• Parallel World Layers — Dual-scene rendering for dream or alternate realms.
• GeoNodes — Map coordinates for visual world navigation.
Status: Planned

───────────────────────────────
Subsystem: Persona & Character
Priority: Immediate
Features:
• Emotion Blend System — Smooth transition between facial states.
• Dynamic Outfit System — Auto clothing changes by story state or world.
• Relationship Heatmaps — Visual indicators of bond or conflict.
• Persona Stats Overlay — Realtime display of trust and stress variables.
• Voice Emotion Sync — Link voice pitch to emotion intensity.
Status: Planned

───────────────────────────────
Subsystem: Audio & Effects
Priority: Immediate
Features:
• Procedural Soundscapes — Generate ambient noise dynamically.
• AI-TTS Voice Pack Manager — Assign custom or generated voices.
• Environmental Audio Zones — Reverb and filters based on location.
• Adaptive Music System — Adjust track layers by mood and dialogue tone.
• SFX Chaining — Combine multiple sound layers for realism.
Status: Planned

───────────────────────────────
Subsystem: Asset & Sprite
Priority: Immediate
Features:
• Pose Library System — Save and reuse multi-character poses.
• Sprite Layer Debugger — Visual stack inspector for assets.
• Texture Compression Profiles — Optimize assets by performance tier.
• Crowd Generator — Procedural background NPC creation.
• Depth Focus Simulation — Apply blur to unfocused characters.
Status: Planned

───────────────────────────────
Subsystem: Playground
Priority: Immediate
Features:
• Director Mode — Frame-by-frame cinematic control timeline.
• Emotion Rewrite Prompts — Auto adjust dialogue and visuals by mood request.
• Prop Injection Prompts — Add or remove objects through text commands.
• Scene Replay Mode — Instant route testing interface.
• Prompt Undo Stack — Revert natural-language edits.
Status: Planned

───────────────────────────────
Subsystem: LoRA & Consistency
Priority: Immediate
Features:
• LoRA Versioning — Snapshot and track LoRA versions with project state.
• Strength Blending — Blend two LoRAs for mixed expressions or outfits.
• Visual QA Comparison — Verify sprite consistency with reference samples.
• Character DNA Profiles — Generate micro-LoRAs for frequent characters.
• Prompt Normalization Engine — Clean prompts for reproducible renders.
Status: Planned

───────────────────────────────
Subsystem: Export & Distribution
Priority: Deferred
Features:
• Smart Asset Bundling — Include only used resources in export.
• Dynamic Translation Export — Generate localization files automatically.
• Quality Profiles — Presets for Preview, HD, and Cinematic rendering.
• VN-to-Video Compilation — Output full story routes as MP4 videos.
• Publishing API — One-click deployment to web or distribution platforms.
Status: Planned

───────────────────────────────
Subsystem: AI-Driven Enhancements
Priority: Deferred
Features:
• Emotion Prediction Model — Infer missing emotional metadata.
• Adaptive Lighting AI — Adjust hue and brightness dynamically.
• Character Coherence Checker — Validate consistency of dialogue tone.
• Story Auto-Tagging — Generate searchable metadata for routes.
Status: Planned

───────────────────────────────
Subsystem: Developer Tools
Priority: Deferred
Features:
• Hot Reload System — Reload assets without restarting the server.
• Version Snapshot Manager — Save full project states pre-render.
• Render Time Analytics — Display per-scene timing and GPU usage.
• Error Heatmap — Visualize failed renders across scenes.
• Collaborative Notes — Comment system inside GUI for teams.
Status: Planned

───────────────────────────────
Version 0.3 Completion Criteria:
• All Immediate-priority features implemented and verified.
• Scene JSON schema updated for new media and animation data.
• GUI capable of editing, previewing, and saving scenes interactively.
• Audio and World Lore systems synchronized for ambience.
• All modules lint-clean, line-budget-compliant, and integrated through API routes.