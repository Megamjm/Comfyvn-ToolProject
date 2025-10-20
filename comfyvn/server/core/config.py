from PySide6.QtGui import QAction
import yaml
from pathlib import Path
CFG_PATH = Path("./data/config.yaml")

DEFAULTS = {
  "project_name": "ComfyVN",
  "renpy_export_path": "./exports/renpy",
  "bridge": {"sillytavern_url": "http://127.0.0.1:8000", "comfyui_url": "http://127.0.0.1:8188"},
}

def load() -> dict:
    if CFG_PATH.exists():
        try:
            return yaml.safe_load(CFG_PATH.read_text()) or DEFAULTS
        except Exception:
            pass
    return DEFAULTS

def save(cfg: dict):
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")