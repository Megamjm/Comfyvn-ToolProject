⚙️ ComfyVN Server Core – Integration Sync v2.3

Date: 2025-10-11
Architect: ComfyVN Architect
Branch: ⚙️ 3. Server Core Production Chat

🧭 Overview

This update unifies all runtime subsystems under a consistent async-safe, event-driven core, synchronizing with GUI v0.3, World v2.3, and Asset v3.1 branches.

It introduces:

WebSocket + SSE event streams for live job feedback

JobManager metadata tracing (origin/token)

ComfyUI Bridge async queuing & polling

World Sync checksum-based pull from SillyTavern

Ren’Py Bridge multi-scene compiler

Audio Manager GUI integration

Mode Manager for runtime profiles

🧩 Edited Modules (Existing Files Only)
Patch	File	Summary	Key Additions
A	comfyvn/app.py	Core routing & subsystem integration	WebSocket + SSE endpoints, /jobs/poll, /audio/*, /lora/*, /worlds/*
B	modules/world_loader.py	Class-based loader w/ SillyTavern sync	SHA-1 checksum diff, 3-state clean-sync system
C	modules/audio_manager.py	GUI toggle manager	Safe toggle/restore, console feedback
I	modules/job_manager.py	Job control + event publishing	origin, token, poll(), async _emit()
J	modules/event_bus.py	Real-time event hub	Async queue broadcast, SSE stream()
K	modules/comfy_bridge.py	ComfyUI REST bridge	queue_and_wait(), background polling thread
L	modules/mode_manager.py	Runtime profile controller	list_modes() helper for GUI dropdown
M	modules/renpy_bridge.py	Ren’Py export bridge	Multi-scene compilation, menu branching, manifest output

ComfyVN Server Core v2.3
------------------------
A modular FastAPI backend coordinating ComfyUI rendering,
Ren’Py export, SillyTavern lore syncing, and GUI control.

Features:
• Async EventBus + WebSocket + SSE job feeds
• Persistent mode, cache, and log systems
• Seamless SillyTavern + LM Studio bridge
• Unified REST endpoints for GUI control
• Ready for GUI v0.3+ (Task Manager Dock integration)
