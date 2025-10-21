from PySide6.QtGui import QAction


def plugin():
    name = "echo"

    def handle(task_type, payload, job_id):
        if task_type != "echo":
            return None
        msg = payload.get("message", "hello")
        return {"ok": True, "result": {"echo": msg}}

    return {"name": name, "handle": handle}
