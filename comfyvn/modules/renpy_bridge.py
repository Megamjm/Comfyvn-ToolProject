# comfyvn/modules/renpy_bridge.py
# ⚙️ 3. Server Core Production Chat — Ren'Py Bridge (multi-scene)  [ComfyVN Architect]

import os
from datetime import datetime
from typing import Dict, Any, List

class RenPyBridge:
    """Converts processed scene plans into Ren'Py .rpy, supports multi-scene compilation."""

    def __init__(self, export_dir: str = "./exports/renpy"):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    # ---------- low-level helpers ----------
    def _fmt_line(self, speaker: str, text: str) -> str:
        speaker = speaker or "Narrator"
        text = text or ""
        return f'    "{speaker}": "{text}"\n'

    def _fmt_header(self, scene_id: str, background: str, cues: List[str]) -> str:
        header = [f"label {scene_id}:", f"    scene {background}"]
        for cue in cues or []:
            header.append(f"    # Cue: {cue}")
        return "\n".join(header) + "\n"

    def _normalize_scene_id(self, scene_id: str) -> str:
        return (scene_id or f"scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}").replace("-", "_")

    # ---------- single-scene ----------
    def scene_to_rpy(self, scene_plan: Dict[str, Any]) -> str:
        """Convert a single scene plan dict into Ren'Py script text."""
        scene_id = self._normalize_scene_id(scene_plan.get("scene_id"))
        background = scene_plan.get("background", "default_room")
        cues = scene_plan.get("stage_cues", [])
        characters = scene_plan.get("characters", [])
        raw_text = scene_plan.get("text", "")
        lines = []

        # naive split: alternate sentences to speakers if provided
        sentences = [s.strip() for s in raw_text.replace("\n", " ").split(". ") if s.strip()]
        if characters:
            for i, sentence in enumerate(sentences or [raw_text]):
                speaker = characters[i % len(characters)].get("name") or f"Char{i+1}"
                lines.append(self._fmt_line(speaker, sentence))
        else:
            for sentence in sentences or [raw_text]:
                lines.append(self._fmt_line("Narrator", sentence))

        # branching (optional)
        choices: List[Dict[str, str]] = scene_plan.get("choices", [])
        menu_block = ""
        if choices:
            menu_block = "    menu:\n"
            for ch in choices:
                label = ch.get("label", "Continue")
                target = self._normalize_scene_id(ch.get("target", ""))
                if not target:
                    continue
                menu_block += f'        "{label}":\n'
                menu_block += f"            jump {target}\n"

        # glue
        script = self._fmt_header(scene_id, background, cues)
        script += "".join(lines)
        if menu_block:
            script += "\n" + menu_block + "\n"
        else:
            script += "    return\n"
        script += "\n"
        return script

    def save_script(self, scene_plan: Dict[str, Any]) -> Dict[str, str]:
        """Save a single-scene .rpy."""
        script_text = self.scene_to_rpy(scene_plan)
        scene_id = self._normalize_scene_id(scene_plan.get("scene_id"))
        file_path = os.path.join(self.export_dir, f"{scene_id}.rpy")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(script_text)
        return {"file": file_path, "scene_id": scene_id, "script_text": script_text}

    # ---------- multi-scene ----------
    def compile_scenes(
        self,
        scenes: List[Dict[str, Any]],
        chapter_name: str | None = None,
        make_entry_label: bool = True,
        entry_label: str | None = None,
    ) -> Dict[str, Any]:
        """
        Compile many scene plans into one .rpy.
        Scenes may include:
          - scene_id, background, text, characters, stage_cues
          - choices: [{label, target}]  -> menu + jumps

        Returns: {file, chapter_label, manifest, script_text}
        """
        if not scenes:
            raise ValueError("No scenes provided to compile.")

        chapter_label = (entry_label or chapter_name or "chapter").replace("-", "_")
        out_file = os.path.join(self.export_dir, f"{chapter_label}.rpy")

        # build manifest & scripts
        manifest = []
        body_parts = []

        # optional entry point that jumps to first scene
        if make_entry_label:
            first_scene_id = self._normalize_scene_id(scenes[0].get("scene_id", "scene_1"))
            entry = (
                f"label {chapter_label}:\n"
                f"    # auto-generated entry\n"
                f"    jump {first_scene_id}\n\n"
            )
            body_parts.append(entry)

        # render each scene
        for s in scenes:
            sid = self._normalize_scene_id(s.get("scene_id"))
            script = self.scene_to_rpy(s)
            body_parts.append(script)
            manifest.append({
                "scene_id": sid,
                "background": s.get("background", "default_room"),
                "has_choices": bool(s.get("choices")),
                "characters": [c.get("name") for c in (s.get("characters") or [])],
            })

        script_text = "\n".join(body_parts)

        with open(out_file, "w", encoding="utf-8") as f:
            f.write("# Generated by ComfyVN RenPyBridge (multi-scene)\n")
            f.write(script_text)

        return {
            "file": out_file,
            "chapter_label": chapter_label,
            "manifest": manifest,
            "script_text": script_text,
        }
