# comfyvn/core/theme_manager.py
from __future__ import annotations

import json
from pathlib import Path

BASE = Path("comfyvn/gui/themes")
PALETTES = BASE / "themes.json"


def _qss_for(pal: dict) -> str:
    bg = pal.get("bg", "#0E1116")
    pbg = pal.get("panel", "#151A22")
    acc = pal.get("accent", "#1AB6B6")
    hi = pal.get("highlight", "#29D7D7")
    tx = pal.get("text", "#E9EEF1")
    bd = pal.get("border", "#1E242F")
    qss = []
    qss.append(
        f"QWidget {{ background: {bg}; color: {tx}; selection-background-color: {acc}; }}"
    )
    qss.append(
        "QMenuBar, QMenu, QToolBar, QDockWidget, QStatusBar, QTabBar, "
        f"QTabWidget, QTreeView, QListView, QTextEdit, QPlainTextEdit {{ background: {pbg}; color: {tx}; border: 1px solid {bd}; }}"
    )
    qss.append(
        f"QPushButton {{ background: {bd}; border: 1px solid {bd}; padding: 6px 10px; border-radius: 6px; }}"
    )
    qss.append(f"QPushButton:hover {{ border-color: {hi}; }}")
    qss.append(f"QPushButton:pressed {{ background: {acc}; }}")
    qss.append(f"QProgressBar::chunk {{ background: {acc}; }}")
    return "\n".join(qss)


def _palettes() -> dict:
    if PALETTES.exists():
        try:
            return json.loads(PALETTES.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def apply_theme(app, name: str = "default_dark"):
    pals = _palettes()
    pal = pals.get(name) or pals.get("default_dark") or {}
    qss_file = BASE / f"{name}.qss"
    if qss_file.exists():
        qss = qss_file.read_text(encoding="utf-8")
    else:
        qss = _qss_for(pal)
    app.setStyleSheet(qss)
