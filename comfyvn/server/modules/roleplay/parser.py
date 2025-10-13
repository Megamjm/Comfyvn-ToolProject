# comfyvn/server/modules/roleplay/parser.py
# 🤝 ComfyVN Roleplay Importer — Phase 3.2 Scaffold
# [Roleplay Import & Collaboration Chat | ComfyVN_Architect]

import re
from typing import List, Dict


class RoleplayParser:
    """Extracts speaker lines and timestamps from raw chat logs."""

    def __init__(self):
        self.speaker_pattern = re.compile(
            r"^(\[?[\d: ]*\]?\s*)([A-Za-z0-9_\- ]+):\s*(.+)$"
        )

    def parse_text(self, raw_text: str) -> List[Dict]:
        lines = []
        for i, line in enumerate(raw_text.splitlines()):
            match = self.speaker_pattern.match(line.strip())
            if match:
                speaker = match.group(2).strip()
                text = match.group(3).strip()
                lines.append({"line_id": i, "speaker": speaker, "text": text})
        return lines
