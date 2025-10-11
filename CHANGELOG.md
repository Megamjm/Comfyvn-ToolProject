ComfyVN ToolProject
Change Log — Version 0.2 Development Branch

────────────────────────────────────────────
Release Type: Major System Alignment Update
Date: 10-10-2025
────────────────────────────────────────────

Summary:
This release establishes the ComfyVN multi-layer architecture, integrating all subsystems into the unified project baseline. It updates documentation, finalizes the system’s rendering structure, adds world-lore and persona logic, and introduces audio and playground foundations. The project now transitions from scaffold to active development phase.

Core Additions:
• Established Project Integration framework to manage all subsystems.
• Added Server Core using FastAPI for unified endpoint handling.
• Introduced Scene Preprocessor for merging world, character, and emotion data.
• Integrated Mode Manager supporting Render Stages 0–4.
• Implemented Audio_Manager with per-type toggles for sound, music, ambience, voice, and FX.
• Completed World_Loader module for cached world-lore and location theming.
• Added Persona_Manager for user avatar display and multi-character layout logic.
• Added NPC_Manager for background crowd rendering with adjustable density.
• Introduced Export_Manager for batch character dump and sprite sheet generation.
• Implemented LoRA_Manager with local cache and search registration.
• Created Playground_Manager and API for live scene mutation and branch creation.
• Added Packaging scripts for Ren’Py export and asset bundling.
• Established Audio, Lore, Character, Environment, and LoRA data directories.

Changes and Improvements:
• Converted documentation to reflect multi-mode rendering and layered architecture.
• Replaced all Flask references with FastAPI to support async processing.
• Standardized scene data schema to include media toggles, render_mode, and npc_background.
• Updated safety system tiers: Safe, Neutral, and Mature.
• Improved README to align with current system design and terminology.
• Added automatic capability detection for hardware and performance scaling.
• Introduced consistent JSON field naming across all modules.

Fixes:
• Corrected initial import paths and module naming inconsistencies.
• Ensured World_Loader loads active world cache correctly.
• Verified cache and export managers reference local directories safely.
• Removed deprecated directory references from prior VNToolchain iteration.

Known Limitations:
• Cinematic (Stage 4) rendering not yet implemented.
• Audio mixing and crossfade functions incomplete.
• Playground prompt parser currently placeholder only.
• GUI configuration panels under development.
• LoRA training disabled pending resource optimization testing.

Next Phase Goals (Version 0.3):
• Complete cinematic video rendering path (ComfyUI workflow integration).
• Expand GUI and Playground scene editors for interactive content creation.
• Add auto-ambience and world-specific audio themes.
• Enable lightweight LoRA training for recurring characters.
• Begin test exports to Ren’Py using finalized Scene JSON structures.

────────────────────────────────────────────
End of Change Log for ComfyVN v0.2