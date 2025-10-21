from PySide6.QtGui import QAction

from comfyvn.core.task_registry import task_registry


class ExtensionJobHooks:
    def __init__(self):
        self._handlers = {}  # name -> func

    def register(self, name, func):
        self._handlers[name] = func

    def run(self, name, payload):
        h = self._handlers.get(name)
        if not h:
            return {"ok": False, "error": "no handler"}
        tid = task_registry.register(name, payload)
        try:
            res = h(payload)
            task_registry.update(tid, "done")
            return {"ok": True, "id": tid, "result": res}
        except Exception as e:
            task_registry.update(tid, "error")
            return {"ok": False, "error": str(e)}


job_hooks = ExtensionJobHooks()
