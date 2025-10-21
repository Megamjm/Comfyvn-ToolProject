from pathlib import Path

from PySide6.QtGui import QAction

logs_dir = Path("logs")
logs_dir.mkdir(parents=True, exist_ok=True)
log_path = logs_dir / "server.log"
gui_log_path = logs_dir / "gui.log"
