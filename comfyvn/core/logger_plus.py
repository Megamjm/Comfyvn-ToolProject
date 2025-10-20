from PySide6.QtGui import QAction
# comfyvn/core/logger_plus.py
# [COMFYVN Architect | v1.0 | this chat]
import sys, time
from comfyvn.core.log_bus import log

def info(msg):  log.info(f"[v1] {msg}")
def warn(msg):  log.warn(f"[v1] {msg}")
def error(msg): log.error(f"[v1] {msg}")