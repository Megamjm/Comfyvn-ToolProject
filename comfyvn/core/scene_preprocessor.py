import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/modules/scene_preprocessor.py
# 🧩 Scene Preprocessor – Mode-Aware Prompt Normalizer (Patch N)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import json
import re
from typing import Any, Dict, List


def preprocess_scene(scene_data: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """
    Prepare scene data for rendering and scripting pipelines.
    Normalizes text, extracts cues, and generates a render-ready prompt.
    """
    scene_text = scene_data.get("text", "")
    characters = scene_data.get("characters", [])
    background = scene_data.get("background", "default_room")

    # -------------------------------------------------
    # 1. Basic Normalization
    # -------------------------------------------------
    cleaned_text = re.sub(r"\s+", " ", scene_text).strip()

    # -------------------------------------------------
    # 2. Extract Stage Directions → structured list
    # -------------------------------------------------
    stage_cues = extract_stage_directions(cleaned_text)

    # -------------------------------------------------
    # 3. Generate Render Prompt
    # -------------------------------------------------
    render_prompt = generate_render_prompt(
        cleaned_text, characters, background, stage_cues, mode
    )

    plan = {
        "mode": mode,
        "text": cleaned_text,
        "characters": characters,
        "background": background,
        "stage_cues": stage_cues,
        "render_ready_prompt": render_prompt,
    }

    print(
        f"[ScenePreprocessor] {mode.upper()} scene prepared: "
        f"{len(characters)} chars, bg='{background}', cues={len(stage_cues)}"
    )
    return plan


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def extract_stage_directions(text: str) -> List[Dict[str, str]]:
    """
    Finds embedded directions like:
      [angry], [fade_in], [bg:forest]
    Returns a list of {"type": <key>, "value": <value>} dicts.
    """
    matches = re.findall(r"\[(.*?)\]", text)
    cues: List[Dict[str, str]] = []
    for m in matches:
        if ":" in m:
            k, v = m.split(":", 1)
            cues.append({"type": k.strip(), "value": v.strip()})
        else:
            cues.append({"type": m.strip(), "value": ""})
    return cues


def generate_render_prompt(
    text: str,
    characters: List[Dict[str, Any]],
    background: str,
    cues: List[Dict[str, str]],
    mode: str,
) -> str:
    """
    Builds a context-aware prompt string for ComfyUI.
    Example:
      "VN scene with Luna in classroom, angry expression. Dialogue: '...'"
    """
    char_names = ", ".join(c.get("name", "unknown") for c in characters)
    cue_summary = " ".join(
        f"{c['type']}:{c['value']}" if c["value"] else c["type"] for c in cues
    )

    mode_prefix = {
        "vn": "Visual Novel scene",
        "rpg": "RPG event",
        "cinematic": "Cinematic cutscene",
        "playground": "Experimental prompt",
    }.get(mode, "Scene")

    prompt = (
        f"{mode_prefix} featuring {char_names or 'no characters'} "
        f"in {background}. {cue_summary}. Dialogue: {text}"
    )
    return prompt
