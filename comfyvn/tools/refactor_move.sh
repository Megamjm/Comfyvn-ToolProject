#!/bin/bash
# ComfyVN v1.2.0 folder migration script

set -e
cd "$(dirname "$0")/../"

echo "🧱 Creating new folder structure..."
mkdir -p comfyvn/core comfyvn/assets comfyvn/integrations comfyvn/gui/widgets comfyvn/utils
touch comfyvn/core/__init__.py comfyvn/assets/__init__.py comfyvn/integrations/__init__.py comfyvn/gui/widgets/__init__.py comfyvn/utils/__init__.py

echo "🚚 Moving files..."
mv comfyvn/modules/mode_manager.py comfyvn/core/ 2>/dev/null || true
mv comfyvn/modules/scene_preprocessor.py comfyvn/core/ 2>/dev/null || true
mv comfyvn/modules/comfy_bridge.py comfyvn/core/bridge_comfyui.py 2>/dev/null || true
mv comfyvn/modules/lm_bridge.py comfyvn/integrations/lmstudio_bridge.py 2>/dev/null || true
mv comfyvn/modules/npc_manager.py comfyvn/assets/ 2>/dev/null || true
mv comfyvn/modules/persona_manager.py comfyvn/assets/ 2>/dev/null || true
mv comfyvn/modules/export_manager.py comfyvn/assets/ 2>/dev/null || true
mv comfyvn/modules/cache_manager.py comfyvn/assets/ 2>/dev/null || true
mv comfyvn/modules/renpy_bridge.py comfyvn/integrations/ 2>/dev/null || true
mv comfyvn/modules/sillytavern_bridge.py comfyvn/integrations/ 2>/dev/null || true
mv comfyvn/modules/workflow_bridge.py comfyvn/integrations/ 2>/dev/null || true
mv comfyvn/gui/components/*.py comfyvn/gui/widgets/ 2>/dev/null || true

echo "🧩 Running import refactor..."
python comfyvn/tools/refactor_imports.py

echo "✅ Migration complete."
