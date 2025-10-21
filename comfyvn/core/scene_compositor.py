import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/modules/scene_compositor.py
# Alpha-aware stacking of PNG layers for scene composition
# ComfyVN_Architect (Asset Sprite Research Branch)

import os
from typing import List, Optional

from PIL import Image


def compose_scene_png(
    layers: List[str], out_path: str, size: Optional[tuple] = None
) -> str:
    """
    layers: list of file paths in draw order [background, props..., characters..., fx]
    out_path: output PNG with alpha preserved
    size: optional (width, height) to force canvas; otherwise background size used
    """
    if not layers:
        raise ValueError("No layers provided")

    # load first layer as base
    base = Image.open(layers[0]).convert("RGBA")
    if size:
        base = base.resize(size, Image.LANCZOS)

    canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
    canvas.alpha_composite(base)

    for p in layers[1:]:
        if not os.path.exists(p):
            continue
        top = Image.open(p).convert("RGBA")
        if size and top.size != base.size:
            top = top.resize(base.size, Image.LANCZOS)
        canvas.alpha_composite(top)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, "PNG")
    return out_path
