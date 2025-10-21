import queue
# comfyvn/core/task_queue.py
# [COMFYVN Architect | v1.3 | this chat]
import threading
import time
import traceback
from typing import Any, Callable, Dict, Optional

from PySide6.QtGui import QAction

from comfyvn.core.event_bus import emit


class Task:
    def __init__(self, name: str, fn: Callable, *args, **kwargs):
        self.name = name
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.id = f"task-{int(time.time()*1000)}"
        self.progress = 0
        self.status = "queued"
        self.error = None

    def set_progress(self, pct: int):
        self.progress = max(0, min(100, int(pct)))
        emit(
            "task.progress",
            {"id": self.id, "name": self.name, "progress": self.progress},
        )

    def run(self):
        self.status = "running"
        emit("task.started", {"id": self.id, "name": self.name})
        try:
            result = self.fn(self, *self.args, **self.kwargs)
            self.status = "done"
            self.progress = 100
            emit("task.finished", {"id": self.id, "name": self.name, "result": result})
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            emit(
                "task.error",
                {
                    "id": self.id,
                    "name": self.name,
                    "error": self.error,
                    "trace": traceback.format_exc(),
                },
            )


class TaskQueue:
    def __init__(self, workers: int = 2):
        self.q = queue.Queue()
        self.workers = []
        self._stop = threading.Event()
        for i in range(max(1, int(workers))):
            t = threading.Thread(target=self._loop, name=f"TaskWorker-{i}", daemon=True)
            t.start()
            self.workers.append(t)

    def _loop(self):
        while not self._stop.is_set():
            try:
                task: Task = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            task.run()
            self.q.task_done()

    def submit(self, name: str, fn: Callable, *args, **kwargs) -> Task:
        task = Task(name, fn, *args, **kwargs)
        self.q.put(task)
        emit("task.enqueued", {"id": task.id, "name": task.name})
        return task

    def stop(self):
        self._stop.set()


# singleton for app
task_queue = TaskQueue(workers=2)
