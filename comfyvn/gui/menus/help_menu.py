import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QMessageBox

from comfyvn.config.runtime_paths import diagnostics_dir
from comfyvn.gui.menus.menu_utils import make_action

logger = logging.getLogger(__name__)

DOCS = [
    ("Import Guide", "docs/IMPORTS_USER_GUIDE.md"),
    ("SillyTavern Bridge", "docs/SILLYTAVERN_BRIDGE.md"),
    ("Legal & Liability", "docs/LEGAL_LIABILITY.md"),
    ("Docking & Layout", "docs/DOCKING_AND_LAYOUT.md"),
    ("Getting Started", "README.md"),
    ("Theme Kits", "docs/THEME_KITS.md"),
    ("Importers & Extractors", "docs/EXTRACTORS.md"),
    ("Persona Importers", "docs/PERSONA_IMPORTERS.md"),
]


def _open_local(path: Path) -> None:
    resolved = path.resolve()
    if not resolved.exists():
        logger.warning("Documentation path missing: %s", resolved)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))


def register_menu(window, menubar):
    menu = menubar.addMenu("Help")
    for label, rel in DOCS:
        path = Path(rel)
        act = QAction(f"📚 {label}", window)
        act.triggered.connect(lambda _, p=path: _open_local(p))
        menu.addAction(act)

    def _open_diagnostics():
        target = diagnostics_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    menu.addAction(make_action("🧾 Diagnostics Folder", window, _open_diagnostics))
    about_act = make_action(
        "ℹ️ About",
        window,
        lambda: QMessageBox.information(
            window,
            "About ComfyVN",
            "ComfyVN Visual Novel Framework\nVersion 4.1 GUI Modular",
        ),
    )
    menu.addAction(about_act)
    return menu
