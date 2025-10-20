from PySide6.QtGui import QAction
# comfyvn/gui/fonts_bootstrap.py
# [Main window update chat] — load TTF/OTF fonts from assets/fonts* at import time
from pathlib import Path
from PySide6.QtGui import QFontDatabase

def ensure_fonts():
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "assets" / "fonts",
        root / "data" / "assets" / "fonts",
    ]
    count = 0
    for d in candidates:
        if not d.exists():
            continue
        for f in list(d.glob("**/*.ttf")) + list(d.glob("**/*.otf")):
            try:
                if QFontDatabase.addApplicationFont(str(f)) != -1:
                    count += 1
            except Exception:
                pass
    return count

# auto-run on import
ensure_fonts()