# ComfyVN Studio Extension API (v0.9+)

## Manifest + Hook Overview
Each folder inside `extensions/` can include an `extension.json` describing the package:

```json
{
  "id": "my.cool.extension",
  "name": "Cool Extension",
  "official": false,
  "version": "0.1.0",
  "description": "Adds a dock with the latest telemetry."
}
```

If present, the Studio lists the extension under **Extensions** with an “Official”/“Imported” separator and exposes the metadata via an info dialog. To add interactive items use the legacy `manifest.json` or a `register(menu_registry)` function as shown below.

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
