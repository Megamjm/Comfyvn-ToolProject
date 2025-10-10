# launch_gui.py
from comfyvn.gui.main_window import MainWindow
from PySide6.QtWidgets import QApplication
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
# comfyvn/gui/main_window.py