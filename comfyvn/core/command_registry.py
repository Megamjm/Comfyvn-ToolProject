# comfyvn/core/command_registry.py
# [COMFYVN Architect | v2.0 | this chat]
from typing import Callable, Dict

from PySide6.QtGui import QAction

from comfyvn.core.log_bus import log


class Command:
    def __init__(self, id: str, title: str, cb: Callable, shortcut: str = ""):
        self.id = id
        self.title = title
        self.cb = cb
        self.shortcut = shortcut


class CommandRegistry:
    def __init__(self):
        self._cmds: Dict[str, Command] = {}

    def register(self, parent, id: str, title: str, cb: Callable, shortcut: str = ""):
        # do NOT bind shortcuts here; ShortcutManager owns keybindings
        self._cmds[id] = Command(id, title, cb, shortcut)

    def unregister(self, id: str):
        self._cmds.pop(id, None)

    def list(self) -> Dict[str, Command]:
        return dict(self._cmds)

    def run(self, id: str):
        cmd = self._cmds.get(id)
        if cmd:
            return cmd.cb()


registry = CommandRegistry()


def register_command(parent, id: str, title: str, cb, shortcut: str = ""):
    registry.register(parent, id, title, cb, shortcut)
