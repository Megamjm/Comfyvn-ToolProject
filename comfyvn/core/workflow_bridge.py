# comfyvn/modules/workflow_bridge.py
# ComfyUI + (future) LM Studio bridge for character/scene renders
# ComfyVN_Architect (Asset Sprite Research Branch)

import os, io, json, base64, time
from typing import Dict, Optional, Tuple
import requests
from PIL import Image  # pillow is common in comfy stacks; if unavailable, replace with png bytes

DEFAULT_COMFYUI = os.getenv("COMFYUI_API", "http://127.0.0.1:8188")  # typical ComfyUI server
DEFAULT_TIMEOUT = float(os.getenv("COMFYUI_TIMEOUT", "45.0"))

def _transparent_png_bytes() -> bytes:
    # Minimal valid 1x1 RGBA PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00"
        b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )

def _png_bytes_from_b64(data_uri: str) -> Optional[bytes]:
    try:
        if data_uri.startswith("data:image"):
            b64 = data_uri.split(",", 1)[1]
        else:
            b64 = data_uri
        return base64.b64decode(b64)
    except Exception:
        return None

def _encode_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def ping_comfyui(api_base: str = DEFAULT_COMFYUI, timeout: float = DEFAULT_TIMEOUT) -> bool:
    try:
        r = requests.get(f"{api_base}/system_stats", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False

def render_character_with_comfyui(
    payload: Dict,
    api_base: str = DEFAULT_COMFYUI,
    timeout: float = DEFAULT_TIMEOUT
) -> Tuple[bytes, Dict]:
    """
    Minimal, generic ComfyUI render: expects a 'workflow' dict or
    builds a trivial pipeline (base->(optional) loras->(optional) controlnets).
    Returns (png_bytes, debug_meta).
    """
    # In production, you'd keep JSON templates per style. For now, accept:
    # payload: { "style_id", "base_model", "lora_stack":[], "controlnets":[], "seed", "transparent":True, ... }
    # Optionally: "workflow" for advanced users (raw Comfy graph)
    # For demo, we call a simple /prompt endpoint if available.

    # 1) If user passed a ready workflow, forward it.
    if "workflow" in payload:
        wf = payload["workflow"]
    else:
        # 2) Build a tiny dummy workflow request.
        # NOTE: This is a placeholder "minimal prompt" style. In your real stack,
        # ship a curated workflow JSON per preset.
        wf = {
            "prompt": {
                "seed": payload.get("seed", 12345),
                "base_model": payload.get("base_model", ""),
                "lora_stack": payload.get("lora_stack", []),
                "controlnets": payload.get("controlnets", []),
                "positive": payload.get("positive", "character, full body, clean lines, transparent background"),
                "negative": payload.get("negative", "low quality, extra limbs"),
                "width": payload.get("width", 768),
                "height": payload.get("height", 1024)
            }
        }

    try:
        # ComfyUI community deployments vary; the most portable path is /prompt (queue a job)
        resp = requests.post(f"{api_base}/prompt", json=wf, timeout=timeout)
        resp.raise_for_status()
        job = resp.json()
        # Pull result: if your ComfyUI build returns a direct image, use that. Otherwise poll /history or /view
        # Here we simulate: look for base64 in response (some forks return images inline)
        b64_img = job.get("image") or job.get("images", [{}])[0].get("image", None)
        if b64_img:
            png = _png_bytes_from_b64(b64_img)
            if png:
                return png, {"origin": "comfyui-inline", "workflow_mode": "inline"}

        # If your instance requires polling /history/<id>, add it here.
        # Fallback if no image found:
        return _transparent_png_bytes(), {"origin": "comfyui-placeholder", "reason": "no_inline_image"}
    except Exception as e:
        return _transparent_png_bytes(), {"origin": "comfyui-error", "error": str(e)}

def render_character(payload: Dict) -> Tuple[bytes, Dict]:
    """
    High-level render call:
    - try ComfyUI
    - (future) try LM Studio or other backends
    - always return alpha-safe PNG bytes + debug meta
    """
    use_comfy = payload.get("backend", "comfyui") == "comfyui"
    if use_comfy and ping_comfyui():
        return render_character_with_comfyui(payload)

    # (Future) LM Studio / other backends can go here using localhost:1234
    # If none available, return a transparent placeholder.
    return _transparent_png_bytes(), {"origin": "fallback", "reason": "no_backend_available_or_offline"}