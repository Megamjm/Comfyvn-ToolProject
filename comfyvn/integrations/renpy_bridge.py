from PySide6.QtGui import QAction
import os
from datetime import datetime
from typing import Dict, Any, List

class RenPyBridge:
    def __init__(self, export_dir: str = "./exports/renpy"):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)
    def _fmt_line(self, speaker: str, text: str) -> str:
        speaker = (speaker or "Narrator").replace('"','\"'); text=(text or "").replace('"','\"')
        return f'    "{speaker}": "{text}"\n'
    def _fmt_header(self, scene_id: str, background: str, cues: List[str]) -> str:
        return f"label {scene_id}:\n    # background: {background}\n    # cues: {', '.join(cues)}\n"
    def _normalize_scene_id(self, scene_id: str) -> str:
        return scene_id.replace('-', '_').replace(' ', '_')
    def scene_to_rpy(self, scene_plan: Dict[str, Any]) -> str:
        sid = self._normalize_scene_id(scene_plan.get("scene_id","scene_"+str(int(datetime.now().timestamp()))))
        bg = scene_plan.get("background") or "bg classroom"; cues = scene_plan.get("cues") or []; lines = scene_plan.get("lines") or []
        buf=[self._fmt_header(sid, bg, cues)] + [self._fmt_line(ln.get('speaker') or 'Narrator', ln.get('text') or '') for ln in lines]
        return "".join(buf)
    def save_script(self, scene_plan: Dict[str, Any]) -> str:
        body = self.scene_to_rpy(scene_plan); fn = os.path.join(self.export_dir, f"{scene_plan.get('scene_id','scene')}.rpy")
        with open(fn, "w", encoding="utf-8") as f: f.write(body)
        return fn
    def compile_scenes(self, scenes: List[Dict[str, Any]], chapter_name: str, make_entry_label: bool, entry_label: str):
        for sc in scenes: self.save_script(sc)
        with open(os.path.join(self.export_dir, f"{chapter_name}_entry.rpy"), "w", encoding="utf-8") as f:
            f.write(f"label {entry_label}:\n    jump {scenes[0].get('scene_id','scene_1')}\n")