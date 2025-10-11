# comfyvn/gui/components/dialog_helpers.py
# [🎨 GUI Code Production Chat]
# Simple helper dialogs for confirm/info/error popups.

from PySide6.QtWidgets import QMessageBox


def info(parent, title: str, text: str):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Information)
    box.exec()


def error(parent, title: str, text: str):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Critical)
    box.exec()


def confirm(parent, title: str, question: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(question)
    box.setIcon(QMessageBox.Question)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes
