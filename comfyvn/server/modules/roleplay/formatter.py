# comfyvn/server/modules/roleplay/formatter.py
# 🤝 Generic Roleplay Formatter — standalone mode

import json, uuid, datetime
from typing import List, Dict, Optional
from .analyzer import RoleplayAnalyzer


class RoleplayFormatter:
    """Converts parsed lines into a neutral ComfyVN scene structure."""

    def __init__(self):
        self.analyzer = RoleplayAnalyzer()

    def format_scene(
        self,
        parsed_lines: List[Dict],
        participants: List[str],
        world: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict:
        scene_id = f"rp_{uuid.uuid4().hex[:8]}"
        lines = [
            {
                "speaker": l["speaker"],
                "text": l["text"],
                "emotion": self.analyzer.analyze_line(l["text"]),
            }
            for l in parsed_lines
        ]
        return {
            "scene_id": scene_id,
            "created": datetime.datetime.now().isoformat(),
            "participants": participants,
            "lines": lines,
            "meta": {
                "import_type": "roleplay_log",
                "source": source or "manual_upload",
                "world_tag": world or "unlinked",
            },
        }

    def save_scene(self, scene_data: Dict, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(scene_data, f, indent=2)
