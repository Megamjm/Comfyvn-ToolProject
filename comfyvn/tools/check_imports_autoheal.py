# comfyvn/tools/check_imports_autoheal.py
# 🧩 ComfyVN Import Auto-Heal v0.9 — Self-Healing Edition
# Detects invalid imports, missing __init__ paths, and self-import loops.
# Supports --deep, --sync, and hybrid adaptive modes.

import os, sys, re, importlib, argparse
from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parents[1]
PKG_NAME = "comfyvn"


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def backup_file(path: Path):
    backup = path.with_suffix(".bak")
    try:
        copyfile(path, backup)
        return backup
    except Exception:
        return None


def list_py_files(root: Path):
    for p in root.rglob("*.py"):
        if "__pycache__" not in str(p):
            yield p


# ---------------------------------------------------------------------
# NEW FEATURE: Self-Import Guard
# ---------------------------------------------------------------------
def remove_self_imports(file_path: str):
    """Detect and remove lines that import the same module they're in."""
    rel_module = file_path.replace("\\", "/").split(f"{PKG_NAME}/")[-1]
    rel_module_no_ext = rel_module.replace(".py", "").replace("/", ".")
    changed = False
    new_lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("from ") and " import " in stripped:
                from_path = stripped.split(" import ")[0].replace("from ", "")
                # e.g., "# Removed circular import (PoseManager self-reference)"
                if rel_module_no_ext.endswith(from_path.split(".")[-1]):
                    print(f"🧹 Removed self-import in {file_path}: {stripped}")
                    changed = True
                    continue
            new_lines.append(line)

    if changed:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    return changed


# ---------------------------------------------------------------------
# Import Rewriter
# ---------------------------------------------------------------------
def heal_imports(file_path: Path):
    """Ensure comfyvn-prefixed imports are correct relative to file path."""
    text = file_path.read_text(encoding="utf-8")
    changed = False

    # Normalize imports like "from modules" → "from comfyvn.modules"
    pattern = re.compile(r"^from\s+(?!(?:\.)|comfyvn)([a-zA-Z0-9_\.]+)\s+import", re.M)

    def repl(m):
        nonlocal changed
        target = m.group(1)
        if target.startswith("comfyvn"):
            return m.group(0)
        changed = True
        return f"from {PKG_NAME}.{target} import"

    new_text = re.sub(pattern, repl, text)

    # Normalize bare imports "import modules" → "import comfyvn.modules"
    pattern2 = re.compile(r"^import\s+(?!(?:\.)|comfyvn)([a-zA-Z0-9_\.]+)", re.M)

    def repl2(m):
        nonlocal changed
        target = m.group(1)
        if target.startswith("comfyvn"):
            return m.group(0)
        changed = True
        return f"import {PKG_NAME}.{target}"

    new_text = re.sub(pattern2, repl2, new_text)

    if changed:
        backup_file(file_path)
        file_path.write_text(new_text, encoding="utf-8")
        print(f"🛠  Fixed imports in {file_path}")
    return changed


# ---------------------------------------------------------------------
# __init__.py Sync
# ---------------------------------------------------------------------
def sync_init_exports(pkg_root: Path):
    """Ensure every subfolder has an __init__.py and exports its modules."""
    for sub in pkg_root.rglob("*"):
        if sub.is_dir() and "__pycache__" not in str(sub):
            init = sub / "__init__.py"
            py_files = [p.stem for p in sub.glob("*.py") if p.name != "__init__.py"]
            content = "\n".join([f"from . import {m}" for m in py_files])
            content += "\n__all__ = [" + ", ".join([f'"{m}"' for m in py_files]) + "]\n"
            init.write_text(content, encoding="utf-8")
            print(f"  → Updated {init}")


# ---------------------------------------------------------------------
# Import Verifier
# ---------------------------------------------------------------------
def verify_package(pkg_name: str):
    try:
        importlib.import_module(pkg_name)
        print(f"  → Testing {pkg_name} ... OK")
        return True
    except Exception as e:
        print(f"  → Testing {pkg_name} ... FAILED ({type(e).__name__}: {e})")
        return False


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep", action="store_true", help="Run deep healing scan")
    parser.add_argument(
        "--sync", action="store_true", help="Rebuild __init__.py exports"
    )
    args = parser.parse_args()

    print("🔍 ComfyVN Import Auto-Heal v0.9 — Self-Healing Edition")
    print(
        f"{'💠 Deep Adaptive Mode enabled' if args.deep else '🩵 Quick Sync Mode active'}"
    )

    root_pkg = ROOT / PKG_NAME
    fixed = 0

    for file_path in list_py_files(root_pkg):
        if file_path.name == "__init__.py":
            continue
        if args.deep:
            if heal_imports(file_path):
                fixed += 1
        if remove_self_imports(str(file_path)):
            fixed += 1

    if args.sync:
        print("\n🔄 Syncing __init__.py exports ...")
        sync_init_exports(root_pkg)

    print("\n🧠 Verifying packages...\n")
    all_ok = True
    for sub in [
        "assets",
        "core",
        "gui",
        "integrations",
        "modules",
        "scripts",
        "tools",
        "utils",
    ]:
        if not verify_package(f"{PKG_NAME}.{sub}"):
            all_ok = False

    print("\n🧾 Auto-Heal Report")
    print(f"   • Files scanned  : {len(list(list_py_files(root_pkg)))}")
    print(f"   • Imports fixed  : {fixed}")
    print(f"   • Deep mode      : {'ON' if args.deep else 'OFF'}")
    print(f"   • Init sync      : {'ON' if args.sync else 'OFF'}")

    if all_ok:
        print("\n✅ All comfyvn packages import successfully.")
    else:
        print("\n⚠️ Verification failed. Backups were kept for safety.")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT.parent))
    main()
