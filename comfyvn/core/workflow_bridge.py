from PySide6.QtGui import QAction
import io
from PIL import Image
def transparent_png_bytes(w: int = 1, h: int = 1) -> bytes:
    img = Image.new("RGBA", (w, h), (0,0,0,0))
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()