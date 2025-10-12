# comfyvn/modules/playground_manager.py
# 🧪 Playground Manager – Scene Mutation Sandbox (Patch E)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

from typing import Dict, List

class PlaygroundManager:
    """
    Provides a lightweight, in-memory scene mutation system.
    Used for quick edits or prompt-driven experimentation
    before committing changes to disk.
    """

    def __init__(self) -> None:
        # { scene_id: [prompts, …] }
        self.history: Dict[str, List[str]] = {}

    # -------------------------------------------------
    # Prompt Application
    # -------------------------------------------------
    def apply_prompt(self, scene_id: str, prompt: str) -> Dict[str, str]:
        """
        Record a mutation prompt for the given scene.
        (Later this can feed into an NLP pipeline or model chain.)
        """
        if not scene_id or not prompt:
            return {"status": "error", "message": "scene_id and prompt required"}
        self.history.setdefault(scene_id, []).append(prompt)
        print(f"[Playground] Applied prompt → {scene_id}: {prompt}")
        return {
            "scene_id": scene_id,
            "prompt": prompt,
            "status": "ok",
            "history_len": len(self.history[scene_id]),
        }

    # -------------------------------------------------
    # History Retrieval
    # -------------------------------------------------
    def get_history(self, scene_id: str) -> List[str]:
        """Return the stored mutation history for a scene."""
        return self.history.get(scene_id, [])