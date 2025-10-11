# comfyvn/modules/persona_manager.py
# 🫂 Persona Manager – Group Layout System (Patch F)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

from typing import List, Dict

class PersonaManager:
    """
    Determines character layout positions for visual novel scenes.
    Provides positional mapping for left/center/right alignment
    and future stage direction (depth, emotion, layering, etc.)
    """

    def __init__(self) -> None:
        self.persona_enabled: bool = True
        self.group_positions: List[str] = ["left", "center", "right"]

    # -------------------------------------------------
    # Layout Arrangement
    # -------------------------------------------------
    def arrange_characters(self, characters: List[Dict[str, str]]) -> Dict[str, str]:
        """
        Assigns each character an on-screen position.
        Wraps positions cyclically if more than 3 characters exist.
        Example input: [{"id": "luna"}, {"id": "caelum"}]
        """
        layout: Dict[str, str] = {}
        if not characters:
            return {"status": "error", "message": "No characters provided"}

        for i, char in enumerate(characters):
            cid = char.get("id") or f"char_{i}"
            layout[cid] = self.group_positions[i % len(self.group_positions)]

        print(f"[PersonaManager] Arranged {len(characters)} → {layout}")
        return layout

    # -------------------------------------------------
    # Toggle Persona Rendering
    # -------------------------------------------------
    def enable_personas(self, state: bool = True) -> bool:
        """Enable or disable persona rendering globally."""
        self.persona_enabled = bool(state)
        print(f"[PersonaManager] Persona rendering → {self.persona_enabled}")
        return self.persona_enabled

    def is_enabled(self) -> bool:
        """Return current global persona toggle."""
        return self.persona_enabled
