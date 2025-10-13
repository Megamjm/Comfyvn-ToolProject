# comfyvn/gui/components/advanced_task_manager_dock.py
# 🧠 Advanced Task Manager Dock — v0.4-dev (Phase 3.4-A)
# CPU / GPU / Queue tabs + WS live feed + reallocation actions
# [🎨 GUI Code Production Chat]

import json, threading, asyncio, requests
from datetime import datetime
from typing import List, Dict

from PySide6.QtCore import Qt, QTimer, QPoint, QThread, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMenu,
    QMessageBox,
)

from comfyvn.gui.components.task_resource_bar import TaskResourceBar
from comfyvn.modules.task_allocator import TaskAllocator


# ------------------------------
# WS worker (async in QThread)
# ------------------------------
class _WSWorker(QThread):
    message = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import websockets  # lazy import to avoid hard dep if unused
        except Exception:
            return
        asyncio.run(self._loop())

    async def _loop(self):
        import asyncio, websockets  # noqa

        while not self._stop:
            try:
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    async for msg in ws:
                        if self._stop:
                            break
                        self.message.emit(msg)
            except Exception:
                await asyncio.sleep(3)


class AdvancedTaskManagerDock(QDockWidget):
    """Tabbed CPU/GPU/Queue job manager with device reallocation."""

    def __init__(self, server_url="http://127.0.0.1:8001", parent=None):
        super().__init__("Advanced Task Manager", parent)
        self.server_url = server_url.rstrip("/")
        self.ws_url = self.server_url.replace("http", "ws") + "/ws/jobs"
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(560)

        self.allocator = TaskAllocator(self.server_url)

        # ---------------- UI ----------------
        root = QWidget(self)
        self.setWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(6, 6, 6, 6)

        # filter + refresh row
        top = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by id/type/status/device…")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._poll_now)
        top.addWidget(self.filter_edit)
        top.addWidget(self.btn_refresh)
        v.addLayout(top)

        # tabs
        self.tabs = QTabWidget()
        self.tbl_cpu = self._make_table()
        self.tbl_gpu = self._make_table()
        self.tbl_queue = self._make_table()
        self.tabs.addTab(self.tbl_cpu, "🧮 CPU")
        self.tabs.addTab(self.tbl_gpu, "🎮 GPU")
        self.tabs.addTab(self.tbl_queue, "🕓 Queue")
        v.addWidget(self.tabs)

        # resource bar (CPU/GPU/RAM live)
        self.resource_bar = TaskResourceBar(self)
        v.addWidget(self.resource_bar)

        # state
        self._latest_jobs: List[Dict] = []

        # events
        self.filter_edit.textChanged.connect(self._apply_filter)
        for tbl in (self.tbl_cpu, self.tbl_gpu, self.tbl_queue):
            tbl.setContextMenuPolicy(Qt.CustomContextMenu)
            tbl.customContextMenuRequested.connect(self._context_menu)
            tbl.cellDoubleClicked.connect(self._open_job_console)

        # timers + ws
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_now)
        self.timer.start(8000)

        self.ws = _WSWorker(self.ws_url)
        self.ws.message.connect(self._on_ws)
        self.ws.start()

        # initial poll
        self._poll_now()

    # ---------- table factory ----------
    def _make_table(self) -> QTableWidget:
        tbl = QTableWidget(0, 6)
        tbl.setHorizontalHeaderLabels(
            ["ID", "Type", "Status", "Progress", "Device", "Created"]
        )
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        return tbl

    # ---------- ws handler ----------
    def _on_ws(self, msg: str):
        try:
            data = json.loads(msg)
            job = data.get("job")
            jobs = data.get("jobs")
            if job:
                # upsert single
                found = False
                for i, j in enumerate(self._latest_jobs):
                    if j.get("id") == job.get("id"):
                        self._latest_jobs[i] = job
                        found = True
                        break
                if not found:
                    self._latest_jobs.append(job)
            elif jobs:
                self._latest_jobs = jobs
            self._refresh_tables()
        except Exception:
            pass

    # ---------- polling ----------
    def _poll_now(self):
        def _work():
            try:
                r = requests.get(f"{self.server_url}/jobs", timeout=6)
                js = r.json() if r.status_code == 200 else {}
                self._latest_jobs = js.get("jobs", [])
                self._refresh_tables()
            except Exception:
                # ignore errors; UI remains
                pass

        threading.Thread(target=_work, daemon=True).start()

    # ---------- render tables ----------
    def _refresh_tables(self):
        cpu_rows, gpu_rows, q_rows = [], [], []
        for j in self._latest_jobs:
            device = (j.get("device") or "cpu").lower()
            status = (j.get("status") or "").lower()
            row = [
                str(j.get("id", "")),
                j.get("type", ""),
                status,
                str(j.get("progress", "")),
                device,
                j.get("created_at", ""),
            ]
            if status in ("queued", "pending"):
                q_rows.append(row)
            elif device.startswith("gpu"):
                gpu_rows.append(row)
            else:
                cpu_rows.append(row)

        def fill(tbl: QTableWidget, rows: List[List[str]]):
            tbl.setRowCount(len(rows))
            for r, cols in enumerate(rows):
                for c, val in enumerate(cols):
                    item = QTableWidgetItem(val)
                    if c == 2:  # status color
                        s = val
                        if s in ("queued", "pending"):
                            item.setBackground(Qt.lightGray)
                        elif s in ("processing", "running", "active"):
                            item.setBackground(Qt.yellow)
                        elif s in ("complete", "done", "success"):
                            item.setBackground(Qt.green)
                        elif s in ("error", "failed"):
                            item.setBackground(Qt.red)
                        elif s in ("cancelled", "stopped"):
                            item.setBackground(Qt.gray)
                    tbl.setItem(r, c, item)

        fill(self.tbl_cpu, cpu_rows)
        fill(self.tbl_gpu, gpu_rows)
        fill(self.tbl_queue, q_rows)
        self._apply_filter()

    # ---------- filtering ----------
    def _apply_filter(self):
        txt = self.filter_edit.text().strip().lower()

        def apply(tbl: QTableWidget):
            for r in range(tbl.rowCount()):
                ok = False
                for c in range(tbl.columnCount()):
                    it = tbl.item(r, c)
                    if it and txt in it.text().lower():
                        ok = True
                        break
                tbl.setRowHidden(r, (not ok) if txt else False)

        for t in (self.tbl_cpu, self.tbl_gpu, self.tbl_queue):
            apply(t)

    # ---------- context menu ----------
    def _context_menu(self, pos: QPoint):
        tbl = self.sender()
        rows = list({i.row() for i in tbl.selectedIndexes()})
        if not rows:
            return
        ids = [tbl.item(r, 0).text() for r in rows if tbl.item(r, 0)]
        devices = {tbl.item(r, 4).text().lower() for r in rows if tbl.item(r, 4)}

        menu = QMenu(self)
        # Reallocation actions
        if devices != {"gpu"}:
            menu.addAction("⚡ Move to GPU", lambda: self._reallocate(ids, "gpu"))
        if devices != {"cpu"}:
            menu.addAction("🧮 Move to CPU", lambda: self._reallocate(ids, "cpu"))
        menu.addSeparator()
        menu.addAction("🛑 Cancel", lambda: self._manage(ids, "kill"))
        menu.addAction("⏸ Pause", lambda: self._manage(ids, "pause"))
        menu.addAction("▶️ Resume", lambda: self._manage(ids, "resume"))
        menu.exec(QCursor.pos())

    # ---------- reallocate / manage ----------
    def _reallocate(self, job_ids: List[str], target: str):
        def work():
            ok, fail = 0, 0
            for jid in job_ids:
                try:
                    res = self.allocator.reallocate(jid, target)
                    ok += 1 if res else 0
                except Exception:
                    fail += 1
            self._poll_now()
            if fail:
                QMessageBox.warning(self, "Reallocate", f"Moved {ok}, failed {fail}.")

        threading.Thread(target=work, daemon=True).start()

    def _manage(self, job_ids: List[str], action: str):
        def work():
            for jid in job_ids:
                try:
                    requests.post(
                        f"{self.server_url}/jobs/{action}",
                        json={"job_id": jid},
                        timeout=6,
                    )
                except Exception:
                    pass
            self._poll_now()

        threading.Thread(target=work, daemon=True).start()

    # ---------- double click ----------
    def _open_job_console(self, row: int, _col: int):
        # Placeholder hook: integrate TaskConsoleWindow here if present
        jid_item = self.sender().item(row, 0)
        if not jid_item:
            return
        jid = jid_item.text()
        QMessageBox.information(
            self,
            "Job",
            f"Open console for job: {jid}\n\n(Integrate TaskConsoleWindow)  # [🎨 GUI Code Production Chat]",
        )


from comfyvn.gui.components.charts.resource_chart_widget import ResourceChartWidget

# Inside your TaskManagerDock or control tab init:
# self.chart_widget = ResourceChartWidget(self)
# vlayout.addWidget(self.chart_widget)
