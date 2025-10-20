from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/asset_manager.py
from pathlib import Path
import json, shutil

ASSET_DB = Path("comfyvn/data/assets.json")

def list_assets(kind=None):
    if ASSET_DB.exists():
        data=json.loads(ASSET_DB.read_text(encoding="utf-8"))
    else:
        data={"images":[],"audio":[],"sprites":[]}
    return data if kind is None else data.get(kind,[])

def register_asset(kind:str,path:str):
    data=list_assets()
    data.setdefault(kind,[]).append(path)
    ASSET_DB.parent.mkdir(parents=True,exist_ok=True)
    ASSET_DB.write_text(json.dumps(data,indent=2),encoding="utf-8")

def import_folder(folder:str,kind:str="images"):
    p=Path(folder)
    for f in p.glob("*.*"):
        if f.suffix.lower() in [".png",".jpg",".jpeg",".wav",".mp3",".ogg",".flac"]:
            register_asset(kind,str(f.resolve()))
    return list_assets(kind)