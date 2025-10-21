# comfyvn/gui/main_window/shell_studio.py  [Studio-090]
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenuBar, QStatusBar


class ShellStudio(QMainWindow):
    def __init__(self, title="ComfyVN Studio"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1360, 860)

        self.mb = QMenuBar(self)
        self.setMenuBar(self.mb)
        self.sb = QStatusBar(self)
        self.setStatusBar(self.sb)
        self.sb.showMessage("Ready")

        self.m_file = self.mb.addMenu("&File")
        self.m_view = self.mb.addMenu("&View")
        self.m_tools = self.mb.addMenu("&Tools")
        self.m_window = self.mb.addMenu("&Window")
        self.m_help = self.mb.addMenu("&Help")

        a_exit = QAction("Exit", self)
        a_exit.triggered.connect(self.close)
        self.m_file.addAction(a_exit)

    def add_view_item(self, text, fn):
        a = QAction(text, self)
        a.triggered.connect(fn)
        self.m_view.addAction(a)
        return a

    def add_tools_item(self, text, fn):
        a = QAction(text, self)
        a.triggered.connect(fn)
        self.m_tools.addAction(a)
        return a
