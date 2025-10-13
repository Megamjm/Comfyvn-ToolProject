# comfyvn/comfyui/nodes/pose_interpolator.py
# Pose Interpolator Node for ComfyUI (ComfyVN_Architect)

import json
from typing import Dict


class PoseInterpolator:
    """
    Inputs:
      - pose_a_json: JSON string ({"pose_id":..., "skeleton":{id:{x,y}}})
      - delta_json: JSON string ({"deltas":{id:{dx,dy}}})
      - t: float in [0,1]
    Output:
      - pose_out_json: JSON string (same schema) with blended skeleton
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pose_a_json": ("STRING", {"multiline": True}),
                "delta_json": ("STRING", {"multiline": True}),
                "t": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "ComfyVN/Pose"

    def run(self, pose_a_json: str, delta_json: str, t: float):
        try:
            pose_a = json.loads(pose_a_json)
            delta = json.loads(delta_json)
        except Exception as e:
            return (json.dumps({"error": f"Invalid JSON: {e}"}),)

        a_sk = pose_a.get("skeleton", {})
        d_sk = delta.get("deltas", {})
        out = {"pose_id": f"{pose_a.get('pose_id','unknown')}__interp", "skeleton": {}}

        for k, a in a_sk.items():
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
            dx = float(d_sk.get(k, {}).get("dx", 0))
            dy = float(d_sk.get(k, {}).get("dy", 0))
            out["skeleton"][k] = {"x": x + dx * t, "y": y + dy * t}

        return (json.dumps(out, indent=2),)


# ComfyUI node registration
NODE_CLASS_MAPPINGS = {"PoseInterpolator": PoseInterpolator}  # (ComfyVN_Architect)


await broadcast_playground_event(
    "interpolate", {"pose_a": pose_a, "delta": delta, "t": t}
)
