import logging
logger = logging.getLogger(__name__)
# tools/refactor_imports.py
# 🔧 ComfyVN Import Refactor Utility – v1.2.0
# Updates old import paths to match new folder structure.
# Run from project root:  python tools/refactor_imports.py

import os, re, pathlib

# mapping of old module paths -> new locations
REWRITE_MAP = {
    # core
    r"from comfyvn\.modules\.mode_manager": "from comfyvn.core.mode_manager",
    r"from comfyvn\.modules\.scene_preprocessor": "from comfyvn.core.scene_preprocessor",
    r"from comfyvn\.modules\.bridge_comfyui": "from comfyvn.core.bridge_comfyui",
    # assets
    r"from comfyvn\.modules\.npc_manager": "from comfyvn.assets.npc_manager",
    r"from comfyvn\.modules\.persona_manager": "from comfyvn.assets.persona_manager",
    r"from comfyvn\.modules\.export_manager": "from comfyvn.assets.export_manager",
    # integrations
    r"from comfyvn\.modules\.lmstudio_bridge": "from comfyvn.modules.orchestration.lmstudio_bridge",
    r"from comfyvn\.modules\.renpy_bridge": "from comfyvn.integrations.renpy_bridge",
    r"from comfyvn\.modules\.sillytavern_bridge": "from comfyvn.integrations.sillytavern_bridge",
}


def rewrite_file(path: pathlib.Path):
    text = path.read_text(encoding="utf-8")
    new_text = text
    for old, new in REWRITE_MAP.items():
        new_text = re.sub(old, new, new_text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print(f"✅ Updated imports in {path}")
    else:
        print(f"— No changes: {path}")


def main():
    root = pathlib.Path(__file__).resolve().parents[1]  # project root
    for py_file in root.rglob("*.py"):
        if "tools" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        rewrite_file(py_file)


if __name__ == "__main__":
    main()