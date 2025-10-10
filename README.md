# VN Suite (Windows) — Filled Scaffold

A Windows-first bundle to orchestrate **SillyTavern → LLM (LM Studio) → ComfyUI → Gallery → Ren’Py**.

## Quick Start (Windows)
1. Double-click **`launch.bat`**.
2. Open **http://127.0.0.1:5000**.
3. Pick a preset, edit workflow JSON, and **Queue Render**.
4. Approve/Reject in **Gallery**, or **Ingest PNG** to pair an existing render.

### Env
- `COMFY_HOST` (default `http://127.0.0.1:8188`)
- `VN_DATA_DIR` (default `./data`)
- `VN_AUTH=1` + `VN_PASSWORD` to enable login
- `LLM_ENDPOINT`, `LLM_API_KEY`, `LLM_MODEL` for LM Studio/OpenAI-compatible endpoints

## Folders
server/  | Flask app
workflows/ | JSON presets (placeholders; paste full ComfyUI workflows)
adapters/ | SillyTavern reader, Comfy client, LLM router
exporters/ | Ren'Py export landing
data/assets/ | Sidecars + PNGs (runtime)
