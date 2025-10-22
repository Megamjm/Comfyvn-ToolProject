from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

LOGGER = logging.getLogger(__name__)


class PreviewStreamPanel(QWidget):
    """Simple viewer that tails preview manifest files written by the hardened bridge."""

    def __init__(self, root: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.root = Path(root or "data/cache/comfy_previews").expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

        self.status = QLabel("Preview stream idle", self)
        self.list = QListWidget(self)
        self.list.setIconSize(QSize(192, 192))

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.list, 1)

        self._last_manifest: Optional[Path] = None
        self._last_mtime: Optional[float] = None

        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.refresh(initial=True)

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.timer.stop()
        super().closeEvent(event)

    def refresh(self, *, initial: bool = False) -> None:
        manifest = self._latest_manifest()
        if manifest is None:
            if initial:
                self.list.clear()
            self.status.setText("No preview manifests found")
            return

        try:
            mtime = manifest.stat().st_mtime
        except OSError as exc:
            LOGGER.debug("Unable to stat manifest %s: %s", manifest, exc)
            return

        if self._last_manifest == manifest and self._last_mtime == mtime:
            return

        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - filesystem dependent
            LOGGER.warning("Failed to read preview manifest %s: %s", manifest, exc)
            return

        previews: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            raw_previews = data.get("previews")
            if isinstance(raw_previews, list):
                previews = [entry for entry in raw_previews if isinstance(entry, dict)]

        self._populate(previews)
        self._last_manifest = manifest
        self._last_mtime = mtime
        self.status.setText(
            f"{manifest.parent.name} · {len(previews)} preview(s) captured"
        )

    def _latest_manifest(self) -> Optional[Path]:
        if not self.root.exists():
            return None
        manifests: List[Path] = []
        try:
            manifests = sorted(
                self.root.glob("**/manifest.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except Exception as exc:  # pragma: no cover - filesystem dependent
            LOGGER.debug("Scanning preview manifests failed: %s", exc)
            return None
        return manifests[0] if manifests else None

    def _populate(self, previews: List[Dict[str, Any]]) -> None:
        self.list.clear()
        for entry in previews:
            local_path = entry.get("local_path")
            if not local_path:
                continue
            path = Path(str(local_path)).expanduser()
            if not path.exists():
                continue
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue
            icon = QIcon(
                pixmap.scaled(
                    self.list.iconSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            item = QListWidgetItem(icon, path.name)
            tooltip = json.dumps(entry, indent=2, ensure_ascii=False)
            item.setToolTip(tooltip)
            self.list.addItem(item)


__all__ = ["PreviewStreamPanel"]
