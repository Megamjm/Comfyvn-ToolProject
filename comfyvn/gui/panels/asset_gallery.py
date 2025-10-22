"""Asset gallery dock with filters, thumbnails, and bulk tag editing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from comfyvn.studio.core.asset_registry import AssetRegistry

LOGGER = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


class _ThumbEmitter(QObject):
    """Signal bridge to forward thumbnail loads back to the UI thread."""

    thumbnail_ready = Signal(str, object)  # uid, Optional[QImage]


class _ThumbnailTask(QRunnable):
    """Background job that loads and scales an image thumbnail."""

    def __init__(self, uid: str, path: Path, emitter: _ThumbEmitter, size: QSize):
        super().__init__()
        self._uid = uid
        self._path = path
        self._emitter = emitter
        self._size = size

    def run(self) -> None:  # pragma: no cover - Qt threading
        image: Optional[QImage] = None
        if self._path.exists() and self._path.is_file():
            if self._path.suffix.lower() in _IMAGE_SUFFIXES:
                candidate = QImage()
                if candidate.load(str(self._path)):
                    image = candidate.scaled(
                        self._size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
        self._emitter.thumbnail_ready.emit(self._uid, image)


class AssetGalleryPanel(QDockWidget):
    """Dock widget showing registry assets with filters and bulk editors."""

    def __init__(
        self,
        registry: AssetRegistry | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Asset Gallery", parent)
        self.setObjectName("AssetGalleryPanel")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)

        self.registry = registry or AssetRegistry()
        self._thumb_pool = QThreadPool(self)
        self._thumb_pool.setMaxThreadCount(4)
        self._thumb_emitter = _ThumbEmitter(self)
        self._thumb_emitter.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._pending_thumbs: set[str] = set()
        self._assets_by_uid: Dict[str, Dict] = {}
        self._asset_items: Dict[str, QListWidgetItem] = {}
        self._all_assets: List[Dict] = []
        self._filtered_assets: List[Dict] = []
        self._thumb_size = QSize(112, 112)
        placeholder = QPixmap(self._thumb_size.width(), self._thumb_size.height())
        placeholder.fill(self.palette().color(self.backgroundRole()))
        self._placeholder_icon = QIcon(placeholder)
        self._hook_refs: List[tuple[str, Callable[[Dict[str, Any]], None]]] = []
        self._pending_refresh = False
        self._register_registry_hooks()
        self.destroyed.connect(self._cleanup_hooks)

        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(6)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(6)

        self._type_filter = QComboBox(container)
        self._type_filter.setMinimumWidth(120)
        self._tag_filter = QComboBox(container)
        self._tag_filter.setMinimumWidth(160)
        self._license_filter = QComboBox(container)
        self._license_filter.setMinimumWidth(140)

        filters_row.addWidget(QLabel("Type:", container))
        filters_row.addWidget(self._type_filter)
        filters_row.addWidget(QLabel("Tag:", container))
        filters_row.addWidget(self._tag_filter)
        filters_row.addWidget(QLabel("License:", container))
        filters_row.addWidget(self._license_filter)
        filters_row.addStretch(1)

        container_layout.addLayout(filters_row)

        self._list_widget = QListWidget(container)
        self._list_widget.setViewMode(QListWidget.IconMode)
        self._list_widget.setResizeMode(QListView.Adjust)
        self._list_widget.setMovement(QListView.Static)
        self._list_widget.setIconSize(self._thumb_size)
        self._list_widget.setSpacing(8)
        self._list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        container_layout.addWidget(self._list_widget, 1)

        editor_box = QGroupBox("Bulk Tag Editor", container)
        editor_layout = QFormLayout(editor_box)
        editor_layout.setContentsMargins(8, 8, 8, 8)
        editor_layout.setSpacing(6)

        self._add_tags_input = QLineEdit(editor_box)
        self._add_tags_input.setPlaceholderText("tag1, tag2, …")
        editor_layout.addRow("Add tags", self._add_tags_input)

        self._remove_tags_input = QLineEdit(editor_box)
        self._remove_tags_input.setPlaceholderText("tag_to_remove, …")
        editor_layout.addRow("Remove tags", self._remove_tags_input)

        license_row = QHBoxLayout()
        self._license_input = QLineEdit(editor_box)
        self._license_input.setPlaceholderText("Leave blank to skip")
        self._license_clear = QCheckBox("Clear", editor_box)
        license_row.addWidget(self._license_input)
        license_row.addWidget(self._license_clear)
        editor_layout.addRow("License", license_row)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)
        self._apply_button = QPushButton("Apply", editor_box)
        self._refresh_button = QPushButton("Refresh", editor_box)
        self._debug_button = QPushButton("Copy Debug JSON", editor_box)
        actions_row.addWidget(self._apply_button)
        actions_row.addWidget(self._refresh_button)
        actions_row.addWidget(self._debug_button)
        actions_row.addStretch(1)
        editor_layout.addRow(actions_row)

        container_layout.addWidget(editor_box)

        self._status_label = QLabel("Loading assets…", container)
        self._status_label.setWordWrap(True)
        container_layout.addWidget(self._status_label)

        self.setWidget(container)

        self._type_filter.currentIndexChanged.connect(self._apply_filters)
        self._tag_filter.currentIndexChanged.connect(self._apply_filters)
        self._license_filter.currentIndexChanged.connect(self._apply_filters)
        self._list_widget.itemSelectionChanged.connect(self._update_status)
        self._refresh_button.clicked.connect(self.refresh_assets)
        self._apply_button.clicked.connect(self._apply_bulk_edits)
        self._debug_button.clicked.connect(self._copy_debug_json)

        self.refresh_assets()

    # ------------------------------------------------------------------
    # Data loading & filtering
    # ------------------------------------------------------------------
    def refresh_assets(self) -> None:
        try:
            assets = self.registry.list_assets()
        except Exception as exc:  # pragma: no cover - Qt heavy
            self._status_label.setText(f"Failed to load assets: {exc}")
            return

        self._all_assets = assets
        self._populate_filters(assets)
        self._apply_filters()

    def _populate_filters(self, assets: Iterable[Dict]) -> None:
        types: List[str] = sorted(
            {str(asset.get("type")) for asset in assets if asset.get("type")}
        )
        tags: List[str] = []
        licenses: List[str] = []
        tag_set: set[str] = set()
        license_set: set[str] = set()
        for asset in assets:
            meta = asset.get("meta") or {}
            for tag in meta.get("tags") or []:
                text = str(tag).strip()
                if text and text not in tag_set:
                    tag_set.add(text)
                    tags.append(text)
            license_tag = meta.get("license")
            if isinstance(license_tag, str):
                norm = license_tag.strip()
                if norm and norm not in license_set:
                    license_set.add(norm)
                    licenses.append(norm)
        tags.sort(key=str.lower)
        licenses.sort(key=str.lower)

        self._rebuild_combo(self._type_filter, types, placeholder="All types")
        self._rebuild_combo(self._tag_filter, tags, placeholder="Any tag")
        self._rebuild_combo(self._license_filter, licenses, placeholder="Any license")

    def _rebuild_combo(
        self,
        combo: QComboBox,
        entries: List[str],
        *,
        placeholder: str = "All",
    ) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for entry in entries:
            combo.addItem(entry, entry)
        if current is not None:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _apply_filters(self) -> None:
        selected_type = self._type_filter.currentData()
        selected_tag = self._tag_filter.currentData()
        selected_license = self._license_filter.currentData()

        filtered: List[Dict] = []
        for asset in self._all_assets:
            if selected_type and asset.get("type") != selected_type:
                continue
            meta = asset.get("meta") or {}
            tags = meta.get("tags") or []
            license_tag = meta.get("license")
            if selected_tag:
                normalized = {str(tag).strip().lower() for tag in tags if tag}
                if selected_tag.lower() not in normalized:
                    continue
            if selected_license:
                if not isinstance(license_tag, str) or (
                    license_tag.strip().lower() != selected_license.lower()
                ):
                    continue
            filtered.append(asset)

        self._render_assets(filtered)

    def _render_assets(self, assets: List[Dict]) -> None:
        self._filtered_assets = assets
        self._assets_by_uid.clear()
        self._asset_items.clear()
        self._list_widget.clear()

        for asset in assets:
            uid = asset.get("uid") or str(asset.get("id"))
            caption = (
                asset.get("meta", {}).get("title") or Path(asset.get("path", "")).name
            )
            item = QListWidgetItem(caption)
            item.setData(Qt.UserRole, uid)
            item.setIcon(self._placeholder_icon)
            tooltip_lines = [f"UID: {uid}"]
            tooltip_lines.append(f"Type: {asset.get('type', '-')}")
            tooltip_lines.append(f"Path: {asset.get('path', '-')}")
            meta = asset.get("meta") or {}
            tags = ", ".join(meta.get("tags") or []) or "(none)"
            tooltip_lines.append(f"Tags: {tags}")
            license_tag = meta.get("license") or "(none)"
            tooltip_lines.append(f"License: {license_tag}")
            item.setToolTip("\n".join(tooltip_lines))
            self._list_widget.addItem(item)
            self._assets_by_uid[uid] = asset
            self._asset_items[uid] = item
            self._schedule_thumbnail(asset)

        self._update_status()

    # ------------------------------------------------------------------
    # Thumbnail helpers
    # ------------------------------------------------------------------
    def _schedule_thumbnail(self, asset: Dict) -> None:
        uid = asset.get("uid")
        if not uid or uid in self._pending_thumbs:
            return
        thumb_path = self.registry.resolve_thumbnail_path(asset)
        candidate = None
        if thumb_path and thumb_path.suffix.lower() in _IMAGE_SUFFIXES:
            candidate = thumb_path
        else:
            asset_path = (self.registry.ASSETS_ROOT / asset.get("path", "")).resolve()
            if asset_path.suffix.lower() in _IMAGE_SUFFIXES:
                candidate = asset_path
        if candidate is None:
            return
        self._pending_thumbs.add(uid)
        task = _ThumbnailTask(uid, candidate, self._thumb_emitter, self._thumb_size)
        self._thumb_pool.start(task)

    def _on_thumbnail_ready(self, uid: str, image: object) -> None:  # pragma: no cover
        self._pending_thumbs.discard(uid)
        item = self._asset_items.get(uid)
        if item is None:
            return
        if isinstance(image, QImage) and not image.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(image)))
        else:
            item.setIcon(self._placeholder_icon)

    def _register_registry_hooks(self) -> None:
        events = (
            AssetRegistry.HOOK_ASSET_REGISTERED,
            AssetRegistry.HOOK_ASSET_META_UPDATED,
            AssetRegistry.HOOK_ASSET_REMOVED,
        )
        for event in events:
            handler = self._make_registry_handler(event)
            try:
                self.registry.add_hook(event, handler)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Failed to bind registry hook %s: %s", event, exc)
                continue
            self._hook_refs.append((event, handler))

    def _make_registry_handler(
        self, event: str
    ) -> Callable[[Dict[str, Any]], None]:  # pragma: no cover - Qt heavy
        def _handler(payload: Dict[str, Any]) -> None:
            self._on_registry_event(event, payload)

        return _handler

    def _on_registry_event(self, event: str, payload: Dict[str, Any]) -> None:
        self._schedule_registry_refresh()
        if event == AssetRegistry.HOOK_ASSET_REMOVED:
            uid = payload.get("uid")
            if isinstance(uid, str):
                self._assets_by_uid.pop(uid, None)
                self._asset_items.pop(uid, None)

    def _schedule_registry_refresh(self) -> None:
        if self._pending_refresh:
            return
        self._pending_refresh = True

        def _refresh() -> None:  # pragma: no cover - Qt heavy
            self._pending_refresh = False
            self.refresh_assets()

        QTimer.singleShot(0, _refresh)

    def _cleanup_hooks(self, _obj: Optional[QObject] = None) -> None:
        for event, handler in self._hook_refs:
            try:
                self.registry.remove_hook(event, handler)
            except Exception:  # pragma: no cover - defensive
                continue
        self._hook_refs.clear()

    # ------------------------------------------------------------------
    # Bulk editing
    # ------------------------------------------------------------------
    def _apply_bulk_edits(self) -> None:
        selected_items = self._list_widget.selectedItems()
        if not selected_items:
            self._status_label.setText("Select one or more assets to edit tags.")
            return
        uids = [item.data(Qt.UserRole) for item in selected_items if item]
        add_tags = [
            t.strip() for t in self._add_tags_input.text().split(",") if t.strip()
        ]
        remove_tags = [
            t.strip() for t in self._remove_tags_input.text().split(",") if t.strip()
        ]
        if (
            not add_tags
            and not remove_tags
            and not (
                self._license_input.text().strip() or self._license_clear.isChecked()
            )
        ):
            self._status_label.setText("No bulk edits specified.")
            return

        license_tag: Optional[str]
        if self._license_clear.isChecked():
            license_tag = ""
        else:
            text = self._license_input.text().strip()
            license_tag = text or None

        try:
            self.registry.bulk_update_tags(
                uids,
                add_tags=add_tags,
                remove_tags=remove_tags,
                license_tag=license_tag,
            )
        except Exception as exc:  # pragma: no cover - Qt heavy
            self._status_label.setText(f"Failed to apply edits: {exc}")
            return

        self._add_tags_input.clear()
        self._remove_tags_input.clear()
        if not self._license_clear.isChecked():
            self._license_input.clear()
        self._license_clear.setChecked(False)
        self.refresh_assets()
        self._status_label.setText(f"Updated {len(uids)} assets.")

    def _copy_debug_json(self) -> None:
        items = self._list_widget.selectedItems()
        if not items:
            self._status_label.setText("Select assets to copy debug JSON.")
            return
        payload: List[Dict[str, Any]] = []
        for item in items:
            uid = item.data(Qt.UserRole)
            asset = self._assets_by_uid.get(uid)
            if asset:
                payload.append(asset)
        if not payload:
            self._status_label.setText("No asset data available for debug copy.")
            return
        try:
            pretty = json.dumps(payload, indent=2, ensure_ascii=False)
            QApplication.clipboard().setText(pretty)
            self._status_label.setText(
                f"Copied debug JSON for {len(payload)} assets to clipboard."
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to copy asset debug JSON: %s", exc)
            self._status_label.setText(f"Copy failed: {exc}")

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def _update_status(self) -> None:
        total = len(self._all_assets)
        shown = len(self._filtered_assets)
        selected = len(self._list_widget.selectedItems())
        self._status_label.setText(
            f"Showing {shown} of {total} assets. Selected {selected}."
        )
