# comfyvn/tools/check_imports.py
# 🧠 ComfyVN Import Checker & Auto-Fixer (v0.4)
# Detects outdated imports, rewrites to new structure, verifies, and cleans backups.

import os
import sys
import re
import importlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

print("🔍 ComfyVN Import Checker & Auto-Fix (v0.4)\n")

# ----------------------------------------------------------------------
# REWRITE MAPPING (Old → New)
# ----------------------------------------------------------------------
REWRITE_MAP = {
    # Core modules
    r"comfyvn\.modules\.mode_manager": "comfyvn.core.mode_manager",
    r"comfyvn\.modules\.scene_preprocessor": "comfyvn.core.scene_preprocessor",
    r"comfyvn\.modules\.comfy_bridge": "comfyvn.core.bridge_comfyui",
    r"comfyvn\.modules\.system_monitor": "comfyvn.core.system_monitor",

    # Assets
    r"comfyvn\.modules\.npc_manager": "comfyvn.assets.npc_manager",
    r"comfyvn\.modules\.persona_manager": "comfyvn.assets.persona_manager",
    r"comfyvn\.modules\.export_manager": "comfyvn.assets.export_manager",
    r"comfyvn\.modules\.cache_manager": "comfyvn.assets.cache_manager",

    # Integrations
    r"comfyvn\.modules\.lm_bridge": "comfyvn.integrations.lmstudio_bridge",
    r"comfyvn\.modules\.workflow_bridge": "comfyvn.integrations.workflow_bridge",
    r"comfyvn\.modules\.renpy_bridge": "comfyvn.integrations.renpy_bridge",
    r"comfyvn\.modules\.sillytavern_bridge": "comfyvn.integrations.sillytavern_bridge",

    # GUI components → widgets
    r"comfyvn\.gui\.components\.": "comfyvn.gui.widgets.",
}

BAD_PATTERNS = [
    re.compile(r"from\s+comfyvn\.gui\.components"),
    re.compile(r"from\s+comfyvn\.modules"),
    re.compile(r"import\s+comfyvn\.modules"),
    re.compile(r"gui\.widgets\.main_window"),
]

# ----------------------------------------------------------------------
# SCAN PHASE
# ----------------------------------------------------------------------
bad_lines = []
for path in ROOT.rglob("*.py"):
    if any(skip in str(path) for skip in ("venv", "site-packages", "__pycache__")):
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if any(p.search(line) for p in BAD_PATTERNS):
            bad_lines.append((path, i, line.strip()))

if bad_lines:
    print("⚠️ Found invalid or outdated imports:")
    for p, i, line in bad_lines:
        print(f"  {p.relative_to(ROOT)}:{i} → {line}")
else:
    print("✅ No outdated imports found.\n")

# ----------------------------------------------------------------------
# AUTO-REWRITE MODE
# ----------------------------------------------------------------------
if "--rewrite" in sys.argv:
    print("\n🧩 Auto-fix mode enabled: rewriting imports...\n")
    touched = []
    for path in {p for p, _, _ in bad_lines}:
        text = path.read_text(encoding="utf-8")
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)

        for old, new in REWRITE_MAP.items():
            text = re.sub(old, new, text)

        path.write_text(text, encoding="utf-8")
        touched.append((path, backup))
        print(f"🛠 Rewritten imports in {path.relative_to(ROOT)} (backup saved as {backup.name})")

# ------------------------------------------------------------------
# VERIFY & CLEANUP PHASE
# ------------------------------------------------------------------
print("\n🧠 Verifying top-level module imports...\n")
modules_dir = ROOT  # ✅ fixed line — no extra indent

all_ok = True
for sub in modules_dir.iterdir():
    if not sub.is_dir() or sub.name.startswith("__"):
        continue
    name = f"comfyvn.{sub.name}"
    print(f"  → Testing {name} ...", end="")
    try:
        importlib.import_module(name)
        print(" OK")
    except Exception as e:
        print(f" FAILED ({type(e).__name__}: {e})")
        all_ok = False

    # Clean up backups only if all imports verified successfully
    if all_ok and touched:
        print("\n🧹 Cleaning backup files...")
        for path, backup in touched:
            try:
                backup.unlink()
                print(f"  Removed {backup.name}")
            except Exception as e:
                print(f"  ⚠️ Could not remove {backup.name}: {e}")
    elif not all_ok:
        print("\n⚠️ Skipping cleanup — verification failed. Backups kept for safety.")
else:
    print("\nℹ️ Run with '--rewrite' to apply fixes and verify.\n")

print("\n✅ Scan complete.")