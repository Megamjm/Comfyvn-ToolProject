# comfyvn/modules/scene_preprocessor.py
# ⚙️ 3. Server Core Production Chat

import re
from typing import Dict, Any

def preprocess_scene(scene_data: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """
    Preprocesses scene data to make it compatible with rendering and scripting pipelines.
    """
    scene_text = scene_data.get("text", "")
    characters = scene_data.get("characters", [])
    background = scene_data.get("background", "default_room")

    # Basic normalization
    cleaned_text = re.sub(r"\s+", " ", scene_text).strip()

    # Extract stage direction cues
    stage_cues = extract_stage_directions(cleaned_text)

    # Output structured plan
    scene_plan = {
        "mode": mode,
        "text": cleaned_text,
        "characters": characters,
        "background": background,
        "stage_cues": stage_cues,
        "render_ready_prompt": generate_render_prompt(cleaned_text, characters, background, stage_cues)
    }

    return scene_plan


def extract_stage_directions(text: str):
    """Finds embedded directions like [angry], [fade_in], [bg:forest]"""
    pattern = r"\[(.*?)\]"
    matches = re.findall(pattern, text)
    return matches


def generate_render_prompt(text: str, characters, background, cues):
    """Builds a render-ready prompt string for ComfyUI."""
    char_names = ", ".join(c.get("name", "unknown") for c in characters)
    cue_text = " ".join(cues)
    prompt = f"Scene with {char_names} in {background}. {cue_text}. Dialogue: {text}"
    return prompt
