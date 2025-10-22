# Chat & Narrator Mode — 2025-10-21

## Intent
- Ship the Phase 2 VN viewer chat surface so Studio operators can mirror scene dialogue, send ad-hoc prompts, and see assistant turns inline without leaving the viewer workspace.
- Layer narrator-mode controls over the same panel so imported scenes can auto-play line-by-line for quick QA or presentation demos without blocking other UI interactions.
- Align SillyTavern integration with the neutral LLM registry: `/api/llm/chat` should forward scene context, honour adapter defaults, and inject SillyTavern active-session metadata when available.

## Touchpoints
- GUI: `comfyvn/gui/central/chat_panel.py` exposed via **Modules → VN Chat** and wired through `MainWindow` + menu defaults.
- Server: `/api/llm/{registry,prompt-pack,chat}` now decorates requests with scene context, SillyTavern snapshots, and returns provider/model metadata alongside assistant replies.
- Bridge: `comfyvn/bridge/st_bridge/session_sync.py` exposes `collect_session_context` + `load_scene_dialogue` so mods/tools can reuse the lightweight context payload; `SillyTavernBridge.get_active()` wraps the plugin’s `/active` endpoint.

## Acceptance Hooks
- VN Chat panel renders stored SceneStore dialogue, accepts prompt input, and toggles narrator playback via a non-blocking timer.
- New chat API replies include `{provider, model, context}` and respect `history/context` payloads; failures should return FastAPI errors with adapter diagnostics.
- Session context helper survives headless environments (bridge optional) and returns enough metadata (`active_world`, `active_character`, persona id) for downstream prompts/debug logs.

## Debug Notes
- To inspect context payloads, hit `GET /api/llm/registry` (provider list) then `POST /api/llm/chat` with `{"scene_id": "<id>", "history": [{"role": "user", "content": "Line"}]}`; the response `context.sillytavern` mirrors the exporter’s `/active` payload when SillyTavern is reachable.
- Scene fallbacks use `SceneStore.load(scene_id)` so authors can test VN chat without SillyTavern; narrator mode simply iterates the same dialogue payload and can be extended to trigger TTS or overlays.
- For modders, the new helpers live alongside existing `sync_session` utilities—hook into them instead of re-implementing SillyTavern probing logic so CLI tools and Studio stay aligned.
