from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QWidget)


class TopBarSelector(QWidget):
    def __init__(self, views, on_select, server):
        super().__init__()
        self.on_select = on_select
        self.server = server
        lay = QHBoxLayout(self)
        self.view_combo = QComboBox()
        self.view_combo.addItems(views)
        self.view_combo.currentTextChanged.connect(self.on_select)
        lay.addWidget(self.view_combo, 2)
        lay.addWidget(QLabel("Server:"))
        self.port_edit = QLineEdit("8001")
        self.port_edit.setFixedWidth(60)
        lay.addWidget(self.port_edit)
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.status = QLabel("● offline")
        lay.addWidget(self.btn_start)
        lay.addWidget(self.btn_stop)
        lay.addWidget(self.status)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)

    def _start(self):
        try:
            port = int(self.port_edit.text())
        except:
            port = 8001
        self.server.start(port=port)

    def _stop(self):
        self.server.stop()

    def set_server_status(self, running: bool):
        self.status.setText("● online" if running else "● offline")
