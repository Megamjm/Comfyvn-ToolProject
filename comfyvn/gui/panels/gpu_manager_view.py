from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)

from comfyvn.core.compute_registry import get_provider_registry
from comfyvn.core.gpu_manager import get_gpu_manager
from comfyvn.core.notifier import notifier


class GPUManagerView(QWidget):
    """Simple GUI for reordering and toggling compute providers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = get_provider_registry()
        self.manager = get_gpu_manager()
        self.setWindowTitle("GPU Manager")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Providers (double-click to toggle active status)"))

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.btn_up = QPushButton("Move Up")
        self.btn_down = QPushButton("Move Down")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_save = QPushButton("Save Order")
        buttons.addWidget(self.btn_up)
        buttons.addWidget(self.btn_down)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_refresh)
        buttons.addWidget(self.btn_save)
        layout.addLayout(buttons)

        self.list_widget.itemDoubleClicked.connect(self.toggle_active)
        self.btn_up.clicked.connect(lambda: self.move(-1))
        self.btn_down.clicked.connect(lambda: self.move(1))
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_save.clicked.connect(self.save_order)

        self.refresh()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _current_row(self) -> int | None:
        row = self.list_widget.currentRow()
        return row if row >= 0 else None

    def refresh(self) -> None:
        self.list_widget.clear()
        providers = self.registry.list()
        for entry in providers:
            pid = entry.get("id")
            active = entry.get("active", False)
            service = entry.get("service", "")
            prefix = "🟢" if active else "⚪"
            self.list_widget.addItem(f"{prefix} {pid} [{service}]")
        self.manager.refresh()

    def move(self, delta: int) -> None:
        row = self._current_row()
        if row is None:
            return
        new_row = max(0, min(self.list_widget.count() - 1, row + delta))
        if new_row == row:
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(new_row, item)
        self.list_widget.setCurrentRow(new_row)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def save_order(self) -> None:
        order: list[str] = []
        for idx in range(self.list_widget.count()):
            text = self.list_widget.item(idx).text()
            pid = text.split()[1]
            order.append(pid)
        self.registry.set_priority_order(order)
        notifier.toast("info", "Provider priority saved.")

    def toggle_active(self, item) -> None:
        pid = item.text().split()[1]
        entry = self.registry.get(pid)
        if not entry:
            QMessageBox.warning(self, "GPU Manager", f"Provider '{pid}' not found.")
            return
        active = not entry.get("active", False)
        self.registry.set_active(pid, active)
        notifier.toast("info", f"{pid} {'activated' if active else 'deactivated'}.")
        self.refresh()
