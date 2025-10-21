from PySide6.QtGui import QAction
from pathlib import Path
import json
from comfyvn.config.runtime_paths import data_dir
POSE_DIRS=[data_dir('poses'), Path('./comfyvn/data/poses')]
class PoseManager:
    def list(self):
        out=[]
        for d in POSE_DIRS:
            d.mkdir(parents=True, exist_ok=True)
            out.extend([str(p) for p in d.glob('**/*.json')])
        return out
    def load(self, path:str):
        try: return json.loads(Path(path).read_text(encoding='utf-8', errors='replace'))
        except Exception: return None
