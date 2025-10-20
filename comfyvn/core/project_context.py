from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/project_context.py
def current() -> str | None:
    from comfyvn.core.workspace_manager import get_last_project
    return get_last_project()