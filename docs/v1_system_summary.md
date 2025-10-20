# ComfyVN System Summary (v1.1.0)
Generated 2025-10-18 01:08:54

## Core Modules
| File | Header | Lines | Summary |
|-------|---------|--------|----------|
| `comfyvn\core\analyzers.py` |  | 23 |  |
| `comfyvn\core\asset_index.py` |  | 28 |  |
| `comfyvn\core\audio_stub.py` |  | 9 |  |
| `comfyvn\core\boot_checks.py` |  | 88 | Fail-fast environment and filesystem checks. |
| `comfyvn\core\bridge_comfyui.py` |  | 78 | Handles all communications with ComfyUI REST API, now async-capable. |
| `comfyvn\core\bridge_local.py` | comfyvn/core/bridge_local.py | 9 |  |
| `comfyvn\core\comfy_bridge.py` |  | 16 |  |
| `comfyvn\core\compute_providers.py` | comfyvn/core/compute_providers.py | 58 |  |
| `comfyvn\core\compute_scheduler.py` | comfyvn/core/compute_scheduler.py | 25 |  |
| `comfyvn\core\db_v05.py` | comfyvn/core/db_v05.py | 85 | Serialize an object to compact JSON string. |
| `comfyvn\core\device_registry.py` |  | 25 |  |
| `comfyvn\core\event_bridge.py` |  | 30 | Lightweight async broadcaster from GUI → Server Core. |
| `comfyvn\core\event_bus.py` | comfyvn/core/event_bus.py | 11 |  |
| `comfyvn\core\event_hub.py` |  | 42 | Simple in-memory fanout hub for publishing and subscribing to events. |
| `comfyvn\core\event_hub_v05.py` | comfyvn/core/event_hub_v05.py | 25 |  |
| `comfyvn\core\extension_loader.py` | comfyvn/core/extension_loader.py | 82 |  |
| `comfyvn\core\feature_registry.py` | comfyvn/core/feature_registry.py | 9 |  |
| `comfyvn\core\feedback_tracker.py` |  | 29 |  |
| `comfyvn\core\flow_registry.py` |  | 99 |  |
| `comfyvn\core\gpu_manager.py` | comfyvn/core/gpu_manager.py | 39 |  |
| `comfyvn\core\health.py` |  | 71 |  |
| `comfyvn\core\hooks.py` | comfyvn/core/hooks.py | 32 |  |
| `comfyvn\core\i18n.py` |  | 20 |  |
| `comfyvn\core\job_lifecycle.py` |  | 58 |  |
| `comfyvn\core\job_manager.py` |  | 165 | Tracks render/export tasks, supports persistence, rotation, and async event publishing. |
| `comfyvn\core\logger_plus.py` | comfyvn/core/logger_plus.py | 8 |  |
| `comfyvn\core\log_bus.py` | comfyvn/core/log_bus.py | 34 |  |
| `comfyvn\core\memory_engine.py` |  | 28 |  |
| `comfyvn\core\mode_manager.py` |  | 72 | Handles the global operational mode for the ComfyVN runtime. |
| `comfyvn\core\music_stub.py` |  | 4 |  |
| `comfyvn\core\node_manager.py` |  | 165 | Minimal node registry with heartbeats and token security. |
| `comfyvn\core\notifier.py` | comfyvn/core/notifier.py | 17 |  |
| `comfyvn\core\ops_routes.py` |  | 108 |  |
| `comfyvn\core\orchestrator.py` |  | 60 | Minimal central coordinator. |
| `comfyvn\core\plugin_events.py` |  | 12 |  |
| `comfyvn\core\plugin_loader.py` |  | 19 |  |
| `comfyvn\core\plugin_manager.py` | comfyvn/core/plugin_manager.py | 13 |  |
| `comfyvn\core\project_context.py` | comfyvn/core/project_context.py | 5 |  |
| `comfyvn\core\render_cache.py` |  | 38 |  |
| `comfyvn\core\replay.py` |  | 10 |  |
| `comfyvn\core\replay_memory.py` |  | 34 |  |
| `comfyvn\core\scene_auto_refresh.py` |  | 32 |  |
| `comfyvn\core\scene_compositor.py` |  | 41 | layers: list of file paths in draw order [background, props..., characters..., fx] |
| `comfyvn\core\scene_preprocessor.py` |  | 102 | Prepare scene data for rendering and scripting pipelines. |
| `comfyvn\core\scene_store.py` |  | 27 |  |
| `comfyvn\core\server_manager.py` | comfyvn/core/server_manager.py | 30 |  |
| `comfyvn\core\session_state.py` | comfyvn/core/session_state.py | 29 |  |
| `comfyvn\core\settings_manager.py` | comfyvn/core/settings_manager.py | 38 |  |
| `comfyvn\core\space_manager.py` | comfyvn/core/space_manager.py | 25 |  |
| `comfyvn\core\state_manager.py` |  | 15 |  |
| `comfyvn\core\st_sync_manager.py` |  | 148 | Compute stable hash of JSON-serializable object. |
| `comfyvn\core\system_monitor.py` |  | 238 | Collects connection states + system hardware metrics and broadcasts to listeners. |
| `comfyvn\core\system_registry.py` |  | 15 |  |
| `comfyvn\core\theme_manager.py` | comfyvn/core/theme_manager.py | 16 |  |
| `comfyvn\core\ui_persistence.py` | comfyvn/core/ui_persistence.py | 15 |  |
| `comfyvn\core\workflow_bridge.py` |  | 5 |  |
| `comfyvn\core\workspace_bus.py` | comfyvn/core/workspace_bus.py | 24 | Shared context across panels (project, selection, modes). |
| `comfyvn\core\workspace_manager.py` | comfyvn/core/workspace_manager.py | 43 |  |
| `comfyvn\core\workspace_templates.py` | comfyvn/core/workspace_templates.py | 30 |  |
| `comfyvn\core\world_loader.py` |  | 146 | Handles loading, merging, caching, and syncing of world lore files. |
| `comfyvn\core\__init__.py` |  | 15 | Auto-generated module exports. |

**Total lines scanned:** 2817
