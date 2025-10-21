import io

from PIL import Image
from PySide6.QtGui import QAction


def transparent_png_bytes(w: int = 1, h: int = 1) -> bytes:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
