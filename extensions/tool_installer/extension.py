"""External Tool Installer links for demonstration purposes."""

from __future__ import annotations

import webbrowser

from comfyvn.core.menu_runtime_bridge import MenuRegistry
from comfyvn.core.notifier import notifier

DOC_URL = "https://github.com/vn-tools/arc_unpacker"


def register(registry: MenuRegistry) -> None:
    registry.add(
        label="Open Tool Installer Docs",
        section="Help",
        callback=_open_docs,
    )


def _open_docs(window) -> None:
    opened = webbrowser.open_new_tab(DOC_URL)
    if opened:
        notifier.toast("info", "Opening external tool installer documentation…")
    else:
        notifier.toast(
            "error", "Unable to launch default browser. Copy the URL manually."
        )
