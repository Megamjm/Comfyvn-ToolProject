# ComfyVN GUI Changelog

---

## GUI v1.1.8-dev — Unified Async Core & Asset System Refactor (Phase 3.8)

### Added
- **Async Core Integration**
  - All REST calls now use `httpx.AsyncClient` for non-blocking server communication.
  - Automatic 10 s polling of `/gui/state` endpoint with connection indicator.
- **Overlay & Dialog Framework**
  - Introduced `ProgressOverlay` (semi-transparent progress bar for async tasks).
  - Added `DialogHelpers` (info/error/confirm) for unified feedback handling.
- **Status Bar Upgrade**
  - Added version badge (`v1.1.8-dev`) and live server connection indicator.
- **World UI Hook**
  - Conditional menu entry for `WorldUI` (when module available).

### Improved
- **Main Window**
  - Refactored for async/await pattern using `run_async()` utility.
  - Integrated Task Manager Dock visibility toggle under View menu.
  - Unified menu structure (File / Tools / View / Settings).
  - Enhanced logging panel with auto-scroll and formatted status output.
- **Asset Browser**
  - Merged multi-select & drag-drop interface with new component system.
  - Added `ProgressOverlay` for export/generation jobs.
  - Integrated threaded REST requests with safe UI callbacks.
  - Unified error/info dialogs and context menus across single and multi-selection modes.
- **Server Bridge**
  - Standardized connection testing and scene dispatch for async use.

### Fixed
- Import path resolution for `comfyvn.gui.*` modules.
- Qt event loop race condition on Linux headless launch (`QT_QPA_PLATFORM=offscreen`).

### Files
- `comfyvn/gui/main_window.py` (updated)
- `comfyvn/gui/asset_browser.py` (updated)
- `comfyvn/gui/components/progress_overlay.py`
- `comfyvn/gui/components/dialog_helpers.py`
- `comfyvn/gui/components/task_manager_dock.py`
- `comfyvn/gui/server_bridge.py`

### Notes
This version unifies all GUI subsystems under the **async core architecture** and prepares for  
Phase 3.9 (“WebSocket Telemetry & Live Render Feed”).  
All prior job history features (Phases 3.5 – 3.7) remain fully compatible.

---

## GUI v1.1.7-dev — Advanced Task Management Console

### Added
- Live Job Console (`TaskConsoleWindow`) with per-job stdout viewer.
- Double-click job → opens floating log window.
- Color-coded job statuses (running/complete/error).
- Persistent 10-file history retained from Phase 3.5.

### Planned Enhancements
- Log export, tray notifications, and WebSocket streaming.

---

## GUI v1.1.6-dev — Job History System

### Added
- Persistent job log system (rotating 10-file JSON archive).
- Context menu → Job History (view, open folder, clear logs).
- Log auto-save on every `/jobs/poll` refresh.

### Files
- `comfyvn/gui/components/task_manager_dock.py` (updated)
- `jobs/` folder inside the user log directory (auto-created)

### Notes
Logs rotate oldest-first when exceeding 10 files.

---

## GUI v1.1.5-dev — Task Manager Dock & Unified Queue

### Added
- Task Manager Dock (pending tasks window) with live polling.
- Right-click actions: Kill, Reset, Move Up, Move Down.
- Dock toggle via View → Task Manager menu.

### Improved
- Asset Browser and Server Control panels now operate under a unified queue visualization.
