## My request for Codex:
Here’s a **single, self-contained Codex stub** you can paste into `docs/CODEX_STUBS/2025-10-22_Live_Fixes_ServerGui_Menu_Gate.md`. It tells the coder to (1) inspect current structure, (2) detect overlapping modules, (3) ask you for confirmation before changing anything that’s already implemented, and (4) otherwise implement the fixes.

It includes exact file targets, safe patch snippets, acceptance checks, and a “Debug & Verification” block.

---

## `docs/CODEX_STUBS/2025-10-22_Live_Fixes_ServerGui_Menu_Gate.md`

> **Check how the current systems work (if any) and then: Update all documentation, architecture, README, change logs, add development notes to the docs channel, ensure there are debug and API hooks for various assets modders/contributors might want.**

# Live Fixes — Server detached boot, Liability Gate, Menus & Panels, Port authority usage

**Intent**
Fix the Windows detached-server launch error, make the **Liability Gate** persist & enforce, wire inert menu items (Import Assets / Ren’Py Exporter / External Tools), simplify the UI (remove demo menus, duplicate bottom strip), and add Tools entries (ST Chat / Persona / Lore / FA / Roleplay). All new code must **use the shared port/base authority** and must not import Qt on the server path.

---

## Safety, pre-flight, and confirmation (do these first)

1. **Create a working branch**

   ```bash
   git checkout -b fix/live-server-gui-menus-gate
   ```

2. **Inventory & search (do not modify yet)**

   * Confirm these files exist and note their status:

     ```
     comfyvn/gui/server_boot.py
     comfyvn/advisory/policy.py
     comfyvn/server/routes/advisory.py
     comfyvn/gui/menu/*.py
     comfyvn/gui/panels/settings_panel.py
     comfyvn/gui/windows/settings_window.py (may not exist)
     comfyvn/gui/panels/export_renpy.py (may not exist)
     comfyvn/gui/panels/tools_installer.py (may not exist)
     comfyvn/config/baseurl_authority.py
     tools/check_current_system.py
     tools/doctor_phase_all.py
     ```
   * Grep for **existing implementations** (we don’t clobber working code):

     ```bash
     rg -n "uvicorn|subprocess|Popen|server_detached" comfyvn/gui/server_boot.py
     rg -n "policy_ack|ack|Liability" comfyvn/advisory comfyvn/server/routes
     rg -n "Import Assets|Ren.?Py Export|External Tool" comfyvn/gui/menu
     rg -n "PYTHONPATH|cwd|creationflags" comfyvn/gui/server_boot.py
     rg -n "discover_base|baseurl_authority" tools/*.py comfyvn/*
     ```
   * **If you find a non-stub or conflicting implementation** for any step below, **pause and ask the user to confirm** whether to:

     * (A) keep the current code and skip the change, or
     * (B) replace with the patch proposed here (we’ll back up the original to `*.bak`).

3. **Backups for any file we’re going to change**

   * For each file you touch: write a `*.bak` copy before edits.

---

## A) Fix: Windows detached server boot (no `comfyvn` import failure)

**File:** `comfyvn/gui/server_boot.py`
**Goal:** spawn with `-m uvicorn`, set `cwd` to repo root, inject `PYTHONPATH`. Avoid Qt imports on server path.

```python
# Phase 2/2 Project Integration Chat — Live Fix Stub
# [PATCH] comfyvn/gui/server_boot.py
import os, sys, subprocess, pathlib, platform

def start_detached_server(host: str, port: int, reload: bool = False):  # chat: LiveFix
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    args = [sys.executable, "-m", "uvicorn", "comfyvn.app:app", "--host", str(host), "--port", str(port)]
    if reload: args.append("--reload")
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, cwd=str(repo_root), env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                     creationflags=creationflags)
```

**Acceptance**

* Launch Studio → “Server: Online”, **no** `ModuleNotFoundError: comfyvn` in `server_detached.log`.
* `curl http://127.0.0.1:<resolved>/health` returns JSON.

---

## B) Liability Gate: persist & enforce

**File:** `comfyvn/advisory/policy.py`
**File:** `comfyvn/server/routes/advisory.py`
**Goal:** atomic save to `config/policy_ack.json`, REST `GET/POST /api/policy/ack`, block risky ops when false.

```python
# Phase 2/2 Project Integration Chat — Live Fix Stub
# [PATCH] comfyvn/advisory/policy.py
import json, os, tempfile
from pathlib import Path

_ACK = Path("config/policy_ack.json")

def get_ack() -> bool:  # chat: LiveFix
    if not _ACK.exists(): return False
    try: return bool(json.loads(_ACK.read_text(encoding="utf-8")).get("ack", False))
    except Exception: return False

def set_ack(v: bool = True) -> None:  # chat: LiveFix
    _ACK.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=str(_ACK.parent), suffix=".tmp")
    tmp.write(json.dumps({"ack": bool(v)}).encode("utf-8")); tmp.flush(); os.fsync(tmp.fileno()); tmp.close()
    os.replace(tmp.name, _ACK)

def require_ack_or_raise():
    if not get_ack():
        raise PermissionError("Liability acknowledgment required")
```

```python
# Phase 2/2 Project Integration Chat — Live Fix Stub
# [PATCH] comfyvn/server/routes/advisory.py
from fastapi import APIRouter, HTTPException
from comfyvn.advisory.policy import get_ack, set_ack

router = APIRouter(prefix="/api/policy", tags=["advisory"])

@router.get("/ack")     # chat: LiveFix
def read_ack(): return {"ack": get_ack()}

@router.post("/ack")    # chat: LiveFix
def write_ack(): set_ack(True); return {"ack": True}
```

**Acceptance**

* First risky action prompts; clicking “Acknowledge” persists.
* Restart app → `/api/policy/ack` returns `{"ack": true}`.
* Export/installer routes can call `require_ack_or_raise()` to block before ack.

---

## C) Wire menu actions & panels

### C-1. Tools → Import Processing / Ren’Py Exporter / External Tools

**File:** `comfyvn/gui/menu/tools_menu.py` (or equivalent)

```python
# Phase 2/2 Project Integration Chat — Live Fix Stub
from PySide6.QtGui import QAction

def build_tools_menu(self, menu):  # chat: LiveFix
    act_import = QAction("Import Assets", self)
    act_import.triggered.connect(lambda: self.open_panel_name("ImportManagerPanel"))
    menu.addAction(act_import)

    act_renpy = QAction("Ren'Py Exporter", self)
    act_renpy.triggered.connect(lambda: self.open_panel_name("RenPyExportPanel"))
    menu.addAction(act_renpy)

    act_ext = QAction("External Tool Installer", self)
    act_ext.triggered.connect(lambda: self.open_panel_name("ToolsInstallerPanel"))
    menu.addAction(act_ext)

    menu.addSeparator()
    for label, panel in [
        ("Import Processing → SillyTavern Chat", "ImportSillyTavernPanel"),
        ("Import Processing → Character/Persona", "PersonaImporterPanel"),
        ("Import Processing → Lore/World", "LoreImporterPanel"),
        ("Import Processing → FurAffinity Images (upload)", "FurAffinityImporterPanel"),
        ("Import Processing → Roleplay (txt/json)", "RoleplayImporterPanel"),
    ]:
        a = QAction(label, self)
        a.triggered.connect(lambda _, p=panel: self.open_panel_name(p))
        menu.addAction(a)
```

> If panels don’t exist yet, create thin panels that post to existing endpoints and render JSON output. Keep comments with **Live Fix Stub** tag.

### C-2. Help menu → open docs

```python
# Phase 2/2 Project Integration Chat — Live Fix Stub
# comfyvn/gui/menu/help_menu.py
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl
from pathlib import Path

DOCS = {
  "Getting Started": "README.md",
  "Theme Kits": "docs/THEME_KITS.md",
  "Importers & Extractors": "docs/EXTRACTORS.md",
  "Persona Importers": "docs/PERSONA_IMPORTERS.md",
  "Liability Gate": "docs/ADVISORY_EXPORT.md",
}

def build_help_menu(self, menu):  # chat: LiveFix
    for label, rel in DOCS.items():
        act = QAction(label, self)
        act.triggered.connect(lambda _, p=rel: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).resolve()))))
        menu.addAction(act)
```

### C-3. Settings as a *window* (modal), not a sticky panel

```python
# Phase 2/2 Project Integration Chat — Live Fix Stub
# comfyvn/gui/windows/settings_window.py
from PySide6.QtWidgets import QDialog, QVBoxLayout
from comfyvn.gui.panels.settings_panel import SettingsPanel

class SettingsWindow(QDialog):  # chat: LiveFix
    def __init__(self, api_client, parent=None):
        super().__init__(parent); self.setWindowTitle("Settings"); self.setModal(True); self.resize(900, 700)
        lay = QVBoxLayout(self); lay.addWidget(SettingsPanel(api_client, parent=self))
```

And wire the menu to open it:

```python
# in Settings menu builder
from comfyvn.gui.windows.settings_window import SettingsWindow  # chat: LiveFix
act = QAction("Open Settings", self)
act.triggered.connect(lambda: SettingsWindow(self.api).exec())
menu.addAction(act)
```

**Acceptance**

* Menus open panels (import/export/tools) with meaningful actions.
* Settings opens in a modal; closing it leaves no stale panel.
* Help items open local docs.

---

## D) Menu cleanup & bottom strip

* **Remove demo menu items**: un-register or guard their registration (e.g., `if DEBUG_EXAMPLES: …`). Move example code under `docs/examples/` for reference.
* **Hide or remove** the duplicate tab strip under the center; keep one primary tab row. Display a concise instruction in the status bar:
  “Start the VN viewer to preview scenes. Tools → Import to ingest assets.”

**Acceptance**

* No “Demo Tool” clutter; single tab row; status bar shows guidance.

---

## E) Ensure **all callers** use the shared base authority

* Confirm these import and call **`comfyvn.config.baseurl_authority.discover_base()`** (or `/api/settings/ports/probe` from UI):

  * `comfyvn/gui/server_boot.py` (already wired)
  * `tools/check_current_system.py` (already wired)
  * `tools/doctor_phase_all.py` (if present)
  * any web client or startup shim

**Acceptance**

* Doctor and checker run without `--base`, find whichever port is free in the ordered list.

---

## Run / Verify (quick)

1. **Restart Studio**, watch server status.
2. Click **Tools → Import Assets** (open panel), **Ren’Py Exporter**, **External Tool Installer**.
3. **Settings** → change ports order; **Probe** shows expected base; save; restart server → base matches first free port.
4. Open **Help** docs.
5. Liability Gate: call `/api/policy/ack` from UI; restart → remains `true`.

---

## Debug & Verification

* [ ] No `ModuleNotFoundError: comfyvn` in `server_detached.log` on Windows.
* [ ] `/api/policy/ack` returns `{"ack": true}` after UI acknowledge; risky routes refuse without ack.
* [ ] Tools menu items open functioning panels (import/export/tools).
* [ ] Demo entries removed from menu; only one bottom tab row; status bar shows guide.
* [ ] `tools/check_current_system.py` and (if available) `tools/doctor_phase_all.py` both resolve base via **base authority**, no hardcoded `:8000/:8001`.
* [ ] README updated with a one-liner about roll-over ports; CHANGELOG entry added.

---

## Notes on conflicts & confirmation

* If any of the target files already contain non-stub implementations (e.g., a different detached-server strategy, an existing policy route), **ask the user**:

  > “I found an existing implementation in **X** that overlaps this patch. Keep existing (skip) or replace with the Live Fix version? (I’ll back up to `*.bak`).”

* If the user chooses “keep”, **leave a TODO** in code linking to this stub and exit that step.

---

## Commit & PR

```bash
git add comfyvn/gui/server_boot.py comfyvn/advisory/policy.py comfyvn/server/routes/advisory.py \
        comfyvn/gui/menu/*.py comfyvn/gui/windows/settings_window.py \
        comfyvn/gui/panels/export_renpy.py comfyvn/gui/panels/tools_installer.py \
        docs/CHANGELOG.md README.md
git commit -m "Live fixes: detached server boot (uvicorn), liability gate persist/enforce, menu wiring, settings window, cleanup"
```

---

If you need the panels (ImportManagerPanel / ToolsInstallerPanel / RenPyExportPanel) stubbed out with minimal working UIs, say the word and I’ll drop those exact class shells next so the menus compile immediately.
