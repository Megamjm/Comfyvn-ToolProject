import logging
logger = logging.getLogger(__name__)
# comfyvn/gui/menus/menu_utils.py
# 🪄 Menu Utilities — icon + shortcut helpers

from PySide6.QtGui import QAction, QIcon, QKeySequence


def make_action(text, parent, callback=None, icon=None, shortcut=None):
    act = QAction(text, parent)
    if icon:
        act.setIcon(QIcon.fromTheme(icon))
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))
    if callback:
        act.triggered.connect(callback)
    return act