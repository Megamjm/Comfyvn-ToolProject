from PySide6.QtGui import QAction
# comfyvn/core/log_bus.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import os, time
class LogBus:
    def __init__(self):
        self.verbose = True
        self.listeners = []
        self.log_dir = "logs"; os.makedirs(self.log_dir, exist_ok=True)
        self.log_path = os.path.join(self.log_dir, "studio.log")

    def set_verbose(self, v: bool): self.verbose = bool(v)
    def attach(self, fn): self.listeners.append(fn)

    def _write(self, line: str):
        try:
            with open(self.log_path, "a", encoding="utf-8") as fp: fp.write(line + "\n")
        except Exception: pass

    def _emit(self, lvl: str, msg: str):
        if lvl == "DEBUG" and not self.verbose: return
        stamp = time.strftime("%H:%M:%S")
        line = f"[{lvl}] {stamp} {msg}"
        print(line)
        self._write(line)
        for fn in list(self.listeners):
            try: fn(lvl, msg)
            except Exception: pass

    def debug(self, m): self._emit("DEBUG", m)
    def info(self, m): self._emit("INFO", m)
    def warn(self, m): self._emit("WARN", m)
    def error(self, m): self._emit("ERROR", m)

log = LogBus()