# ComfyVN Studio Extension API (v0.9+)

## Hook Events
| Event | Args | Purpose |
|-------|------|----------|
| studio.register_panel | (name: str, widget_cls: Callable[[], QWidget], area: Qt.DockWidgetArea=Qt.RightDockWidgetArea) | Register a new dockable panel in Studio |

## Example
```python
from comfyvn.core import hooks
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

def register_panel():
    hooks.emit("studio.register_panel", "My Custom Tool", lambda: QLabel("Hello"), Qt.LeftDockWidgetArea)

register_panel()
