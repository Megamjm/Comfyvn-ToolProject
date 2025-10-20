from PySide6.QtGui import QAction
# comfyvn/gui/utils/script_runner.py
import os, subprocess, threading, shlex
from datetime import datetime
from PySide6.QtWidgets import QMessageBox
class ScriptRunner:
    def __init__(self, parent): self.parent=parent; self._busy=False
    def run_sequence(self, title: str, cmdlist: list[list[str]], env_overrides: dict|None=None):
        if self._busy: return self._msg("Another script sequence is running. Please wait.")
        self._busy=True; threading.Thread(target=self._run,args=(title,cmdlist,env_overrides or {}),daemon=True).start()
    def _run(self,title,cmds,env_overrides):
        env=os.environ.copy(); env.update(env_overrides or {}); lines=[f"[{datetime.now().isoformat()}] BEGIN: {title}"]; ok=True
        for cmd in cmds:
            lines.append("$ "+" ".join(shlex.quote(c) for c in cmd))
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,check=False,env=env)
                if p.stdout: lines.append(p.stdout.strip())
                if p.stderr: lines.append(p.stderr.strip())
                if p.returncode!=0: ok=False; lines.append(f"RETURN CODE: {p.returncode}"); break
            except Exception as e:
                ok=False; lines.append(f"EXCEPTION: {e}"); break
        lines.append(f"[{datetime.now().isoformat()}] END: {title} (ok={ok})"); log_text="\n".join(lines)
        try:
            if hasattr(self.parent,"task_dock") and hasattr(self.parent.task_dock,"append_log"):
                self.parent.task_dock.append_log(title,log_text)
        except Exception: pass
        self._msg(f"{title}\n\n{'Success' if ok else 'Failed'}\n\nLogs captured."); self._busy=False
    def _msg(self,text:str):
        dlg=QMessageBox(self.parent); dlg.setWindowTitle("Script Runner"); dlg.setText(text); dlg.setIcon(QMessageBox.Information); dlg.exec()