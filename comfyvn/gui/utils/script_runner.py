from PySide6.QtGui import QAction
# comfyvn/gui/utils/script_runner.py
import logging
import os, subprocess, threading, shlex
from datetime import datetime
from typing import Callable, List
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)

class ScriptRunner:
    def __init__(self, parent):
        self.parent = parent
        self._busy = False
        self._listeners: List[Callable[[bool, str], None]] = []

    def register_listener(self, callback: Callable[[bool, str], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def run_sequence(self, title: str, cmdlist: list[list[str]], env_overrides: dict | None = None):
        if self._busy:
            self._msg("Another script sequence is running. Please wait.")
            return
        self._busy = True
        threading.Thread(target=self._run, args=(title, cmdlist, env_overrides or {}), daemon=True).start()

    def _run(self, title, cmds, env_overrides):
        env = os.environ.copy()
        env.update(env_overrides or {})
        lines = [f"[{datetime.now().isoformat()}] BEGIN: {title}"]
        ok = True
        for cmd in cmds:
            lines.append("$ " + " ".join(shlex.quote(c) for c in cmd))
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
                if proc.stdout:
                    lines.append(proc.stdout.strip())
                if proc.stderr:
                    lines.append(proc.stderr.strip())
                if proc.returncode != 0:
                    ok = False
                    lines.append(f"RETURN CODE: {proc.returncode}")
                    break
            except Exception as exc:
                ok = False
                lines.append(f"EXCEPTION: {exc}")
                logger.exception("Script sequence failed (%s)", title)
                break
        lines.append(f"[{datetime.now().isoformat()}] END: {title} (ok={ok})")
        log_text = "\n".join(lines)
        if ok:
            logger.info("Script sequence completed: %s", title)
        else:
            logger.warning("Script sequence failed: %s", title)
        try:
            if hasattr(self.parent, "task_dock") and hasattr(self.parent.task_dock, "append_log"):
                self.parent.task_dock.append_log(title, log_text)
        except Exception:
            logger.debug("Unable to append script log to task dock.", exc_info=True)
        self._notify_listeners(ok, log_text)
        self._msg(f"{title}\n\n{'Success' if ok else 'Failed'}\n\nLogs captured.")
        self._busy = False

    def _notify_listeners(self, ok: bool, log_text: str) -> None:
        for callback in list(self._listeners):
            try:
                callback(ok, log_text)
            except Exception:
                logger.debug("Script listener callback failed.", exc_info=True)

    def _msg(self, text: str):
        dlg = QMessageBox(self.parent)
        dlg.setWindowTitle("Script Runner")
        dlg.setText(text)
        dlg.setIcon(QMessageBox.Information)
        dlg.exec()
