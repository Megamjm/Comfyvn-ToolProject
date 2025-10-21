from __future__ import annotations

import json
import threading
# comfyvn/extensions/import_manager/manager.py
import time
import zipfile
from pathlib import Path

from PySide6.QtGui import QAction

from comfyvn.core.task_registry import task_registry


class ImportManager:
    def __init__(self, data_dir="data/assets"):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def import_file(self, path: str):
        item = task_registry.create("import", f"Importing {Path(path).name}")
        t = threading.Thread(target=self._do_import, args=(item.id, path), daemon=True)
        t.start()
        return item.id

    def _do_import(self, tid: str, path: str):
        task_registry.update(tid, status="running", message="Extracting assets…")
        p = Path(path)
        dest = self.root / p.stem
        dest.mkdir(exist_ok=True)
        try:
            if p.suffix == ".zip" or p.suffix == ".pak":
                with zipfile.ZipFile(p, "r") as zf:
                    zf.extractall(dest)
            elif p.suffix == ".json":
                shutil.copy2(p, dest / p.name)
            else:
                task_registry.update(tid, status="error", message="Unsupported type")
                return
            time.sleep(1.2)
            task_registry.update(tid, status="done", message=f"Imported → {dest}")
        except Exception as e:
            task_registry.update(tid, status="error", message=str(e))


import_manager = ImportManager()
