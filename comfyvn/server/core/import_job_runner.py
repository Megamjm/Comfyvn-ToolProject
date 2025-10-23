from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from comfyvn.server.core.import_status import import_status_store


class ImportJobRunner:
    """
    Helper that wires job status updates, log management, and retry handling.

    Usage::

        runner = ImportJobRunner("roleplay", job_id, task_id=task_id, log_path=path)
        runner.run(lambda ctx: process(ctx))
    """

    def __init__(
        self,
        kind: str,
        job_id: str | int,
        *,
        task_id: Optional[str] = None,
        log_path: Optional[Path | str] = None,
        max_attempts: int = 1,
        links: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        self.kind = str(kind or "generic")
        self.job_id = str(job_id)
        self.task_id = task_id
        self.log_path = Path(log_path).expanduser().resolve() if log_path else None
        self.max_attempts = max(1, int(max_attempts or 1))
        self._lock = threading.Lock()

        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.touch(exist_ok=True)

        status_links = dict(links or {})
        if task_id and "logs" not in status_links and self.log_path:
            status_links["logs"] = f"/jobs/logs/{task_id}"

        status_meta = dict(meta or {})
        if self.log_path:
            status_meta.setdefault("log_path", str(self.log_path))

        import_status_store.register(
            self.kind,
            self.job_id,
            state="queued",
            percent=0.0,
            task_id=task_id,
            logs_path=str(self.log_path) if self.log_path else None,
            max_attempts=self.max_attempts,
            links=status_links or None,
            meta=status_meta or None,
        )

    # ------------------------------------------------------------------ logging
    def log(self, message: str) -> None:
        if not self.log_path:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        line = f"[{timestamp}] {message.rstrip()}\n"
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def append(self, message: str) -> None:
        """Alias for :meth:`log`."""
        self.log(message)

    # ------------------------------------------------------------------ status
    def update_status(
        self,
        *,
        state: Optional[str] = None,
        percent: Optional[float] = None,
        message: Optional[str] = None,
        stage: Optional[str] = None,
        detail: Optional[str] = None,
        links: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
        attempt: Optional[int] = None,
    ) -> None:
        import_status_store.update(
            self.job_id,
            state=state,
            percent=percent,
            message=message,
            stage=stage,
            detail=detail,
            links=links,
            meta=meta,
            attempts=attempt,
        )

    # ------------------------------------------------------------------ execution
    def run(self, fn: Callable[["ImportJobRunner"], Any]) -> Any:
        attempt = 0
        last_exc: Optional[BaseException] = None
        while attempt < self.max_attempts:
            attempt += 1
            self.update_status(
                state="running",
                message=f"Attempt {attempt}/{self.max_attempts}",
                percent=5.0 if attempt == 1 else None,
                stage="attempt",
                detail=f"attempt={attempt}",
                meta={"attempt": attempt},
                attempt=attempt,
            )
            try:
                result = fn(self)
                self.update_status(
                    state="done",
                    percent=100.0,
                    message="Import completed",
                    stage="completed",
                    detail="job completed",
                    attempt=attempt,
                )
                return result
            except Exception as exc:  # pragma: no cover - error path
                last_exc = exc
                tb = traceback.format_exc()
                self.log(f"[error] attempt {attempt} failed: {exc}\n{tb}")
                self.update_status(
                    state="error",
                    message=str(exc),
                    stage="error",
                    detail=f"attempt={attempt}",
                    percent=0.0 if attempt == self.max_attempts else None,
                    meta={"exception": str(exc), "traceback": tb},
                )
                if attempt >= self.max_attempts:
                    break
                time.sleep(1.0)
        if last_exc:
            raise last_exc
        raise RuntimeError("import job aborted without execution")
