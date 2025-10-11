ComfyVN — Visual Novel Toolchain
Version: 0.2 Development Branch
License: GPL-3.0

Description:
ComfyVN is a modular, AI-assisted Visual Novel production system designed to bridge ComfyUI, SillyTavern, and Ren’Py into a unified creative pipeline. It converts AI-driven dialogues or existing chat logs into structured, playable visual novels with dynamic rendering, layered sprites, and scalable interaction depth.

Project Objective:
To create a flexible multi-mode Visual Novel engine that can:
• Reuse and render text-based chat sessions as VN storylines.
• Integrate ComfyUI for generative art and scene rendering.
• Support Ren’Py for classic VN presentation and export.
• Leverage SillyTavern for adaptive dialogue logic and memory systems.
• Allow interactive live generation modes for dynamic storytelling.

Core Systems Overview:

Logic Layer (SillyTavern Integration)
Handles dialogue, emotion inference, memory, and branching logic.

Render Layer (ComfyUI + Server Core)
Generates sprites, environments, and effects dynamically based on structured scene data.

Presentation Layer (Ren’Py)
Displays the story as a fully navigable visual novel.

Render Stages:
0 — Classic VN (static)
1 — Reactive VN (expressions auto-sync per line)
2 — Active VN (animated entries, persona sprite support)
3 — Semi-Live VN (basic 2D world movement)
4 — Cinematic VN (AI-generated video or advanced FX)

World Lore Integration:
The system reads world-lore JSON files to automatically set environmental themes, props, colors, and ambience for each scene. The World_Loader module maintains cached world profiles and dynamically merges location and faction data into rendering tasks.

Persona and Group Logic:
User avatars can appear as characters, mirror expressions, or share frame space with dialogue participants. Multi-character scenes are arranged automatically using Persona_Manager for spatial layout and group focus.

Audio and Effects:
Audio_Manager manages toggles for sound, music, ambience, voice, and FX. Each media type can be globally or per-scene controlled. Fallback detection automatically disables features unsupported by the host hardware.

Asset and Sprite System:
Handles sprite composition, background NPC generation, and asset caching. Export_Manager provides batch character dumps for all expressions, poses, and outfits. NPC_Manager populates background crowds as faceless silhouettes for immersion.

Scene Preprocessing:
Scene_Preprocessor merges world, character, emotion, and environment data into a unified Scene JSON format. This serves as the primary contract between all subsystems.

Playground System:
A live editing environment that allows scene modification through natural-language prompts. Users can change lighting, emotions, or setting details and commit changes as new narrative branches.

LoRA Management:
LoRA_Manager searches, registers, and caches character or object LoRAs for consistent visual reproduction. Optional lightweight training may be enabled for recurring characters or assets.

Server Core:
The FastAPI server routes all subsystem operations. Endpoints cover chat ingestion, scene preprocessing, rendering, LoRA search, asset export, safety profiles, and playground operations.

Packaging and Export:
Ren’Py export scripts convert processed scene graphs into .rpy files for final VN assembly. Asset bundles and metadata are packaged for deployment or distribution.

Performance Profiles:
ComfyVN dynamically scales based on detected hardware capabilities, disabling or reducing high-cost rendering and media when necessary.

Safety and Content Controls:
Three safety tiers (Safe, Neutral, Mature) govern rendering limits and filtering behavior. Each prompt or generation task is validated through the safety manager before execution.

Development Phase Summary (as of version 0.2):
• All subsystem scaffolds established.
• Core server endpoints defined.
• World_Loader integrated and verified.
• Audio toggles and environment injection in active development.
• Playground mutation API under construction.
• GUI integration ongoing.
• LoRA caching functional; training disabled by default.

Next Objectives:
• Complete full render mode switching via Mode_Manager.
• Implement world-aware ambience defaults.
• Expand GUI for scene editing and system configuration.
• Begin cinematic renderer integration (Stage 4).
• Complete Playground mutation and export testing.