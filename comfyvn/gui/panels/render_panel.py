from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction
# comfyvn/gui/panels/render_panel.py
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from comfyvn.gui.services.render_service import RenderService


class _PollWorker(QObject):
    result = Signal(dict)

    def __init__(self, base, jid):
        super().__init__()
        self.base = base
        self.jid = jid

    def run(self):
        try:
            r = RenderService(self.base).status(self.jid)
            self.result.emit({"jid": self.jid, "data": r})
        except Exception as e:
            self.result.emit({"jid": self.jid, "data": {"ok": False, "error": str(e)}})


class RenderPanel(QWidget):
    """Render Queue with live polling. Thumbnails stub."""

    def __init__(self, base: str = "http://127.0.0.1:8001"):
        super().__init__()
        self.base = base
        self.service = RenderService(base=base)
        v = QVBoxLayout(self)

        hb = QHBoxLayout()
        self.btn_submit = QPushButton("Submit Dummy Render")
        self.btn_refresh = QPushButton("Refresh")
        hb.addWidget(self.btn_submit)
        hb.addWidget(self.btn_refresh)
        hb.addStretch(1)
        v.addLayout(hb)

        self.list = QListWidget(self)
        v.addWidget(self.list, 1)
        self.lbl = QLabel("", self)
        v.addWidget(self.lbl)

        self.btn_submit.clicked.connect(self._submit)
        self.btn_refresh.clicked.connect(self._refresh)

        self.timer = QTimer(self)
        self.timer.setInterval(1200)
        self.timer.timeout.connect(self._poll_all)
        self.timer.start()

    def _submit(self):
        res = self.service.submit_dummy()
        if not res.get("ok"):
            self.lbl.setText(f"Submit failed: {res}")
            return
        jid = res.get("id")
        it = QListWidgetItem(f"{jid} — queued (0%)")
        it.setData(Qt.UserRole, jid)
        self.list.addItem(it)
        self.lbl.setText(f"Submitted {jid}")

    def _refresh(self):
        self._poll_all()

    def _poll_all(self):
        # non-blocking: worker thread per item
        for row in range(self.list.count()):
            it = self.list.item(row)
            jid = it.data(Qt.UserRole)
            self._poll_one(it, jid)

    def _poll_one(self, item: QListWidgetItem, jid: str):
        th = QThread(self)
        wk = _PollWorker(self.base, jid)
        wk.moveToThread(th)
        wk.result.connect(lambda payload: self._on_result(item, payload))
        th.started.connect(wk.run)
        th.start()

    def _on_result(self, item: QListWidgetItem, payload: dict):
        d = payload.get("data", {})
        if not d.get("ok"):
            item.setText(f"{payload.get('jid')} — error")
            return
        job = d.get("job", {})
        item.setText(f"{job.get('id')} — {job.get('status')} ({job.get('progress')}%)")
