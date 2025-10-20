from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/core/job_manager.py
import time, threading, heapq, uuid, json
from comfyvn.core.event_hub import EventHub
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional
from pathlib import Path
from comfyvn.ext.plugins import PluginManager

DEFAULT_QUEUE = "default"

@dataclass(order=True)
class QItem:
    due: float
    priority: int
    seq: int
    queue: str = field(compare=False)
    id: str = field(compare=False)
    type: str = field(compare=False)
    payload: dict = field(compare=False)
    retries: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=0)
    backoff: float = field(compare=False, default=1.5)
    attempts: int = field(compare=False, default=0)

class RateLimiter:
    def __init__(self, rate_per_sec: float):
        self.rate = float(rate_per_sec)
        self.tokens = float(rate_per_sec)
        self.last = time.time()
        self.lock = threading.Lock()
    def allow(self) -> bool:
        with self.lock:
            now = time.time()
            self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

class JobManager:
    """Advanced orchestrated job manager with DLQ, rate limits, retries, and snapshot state."""
    def __init__(self, *, event_bus=None, plugins: PluginManager|None=None):
        self.pm = plugins or PluginManager()
        self.event_bus = event_bus
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.q: List[QItem] = []
        self.seq = 0
        self.running = True
        self.rate_limits: Dict[str, RateLimiter] = {}
        self.locks: Dict[str, float] = {}
        self.dlq: List[dict] = []
        self._jobs: Dict[str, dict] = {}  # restore for telemetry compatibility
        self.events_path = Path("./data/jobs")
        self.events_path.mkdir(parents=True, exist_ok=True)
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    # --- queue control ---
    def set_rate_limit(self, queue: str, per_sec: float):
        self.rate_limits[queue] = RateLimiter(per_sec)
    def acquire_lock(self, name: str, ttl: float) -> bool:
        with self.lock:
            now = time.time()
            cur = self.locks.get(name, 0)
            if cur > now: return False
            self.locks[name] = now + ttl
            return True
    def release_lock(self, name: str):
        with self.lock: self.locks.pop(name, None)

    # --- enqueue & worker ---
    def enqueue(self, typ: str, payload: dict, *, retries: int=0, priority: int=0, delay: float=0.0,
                queue: str=DEFAULT_QUEUE, backoff: float=1.5) -> str:
        with self.lock:
            jid = payload.get("id") or uuid.uuid4().hex[:12]
            due = time.time() + max(0.0, float(delay))
            self.seq += 1
            qi = QItem(
                due=due, priority=-int(priority), seq=self.seq,
                queue=queue or DEFAULT_QUEUE, id=jid, type=typ,
                payload=dict(payload or {}, id=jid),
                retries=int(retries), max_retries=int(retries), backoff=float(backoff)
            )
            heapq.heappush(self.q, qi)
            self._jobs[jid] = dict(qi.payload, status="queued", created=time.time())
            self.cond.notify_all()
            return jid

    def _pop_ready(self) -> Optional[QItem]:
        now = time.time()
        if not self.q: return None
        qi = self.q[0]
        if qi.due > now: return None
        heapq.heappop(self.q)
        return qi

    def _loop(self):
        while self.running:
            with self.lock:
                qi = self._pop_ready()
                if qi is None:
                    t = 0.25
                    if self.q:
                        nxt = max(0.0, self.q[0].due - time.time())
                        t = min(1.0, max(0.05, nxt))
                    self.cond.wait(timeout=t)
                    continue
            lim = self.rate_limits.get(qi.queue)
            if lim and not lim.allow():
                with self.lock:
                    qi.due = time.time() + 1.0
                    heapq.heappush(self.q, qi)
                continue
            ok, res, err = self._execute(qi)
            with self.lock:
                job = self._jobs.get(qi.id, {})
                job["last_update"] = time.time()
                job["status"] = "done" if ok else "failed"
                job["error"] = err
                self._jobs[qi.id] = job
            if not ok:
                if qi.retries > 0:
                    qi.retries -= 1; qi.attempts += 1
                    delay = (qi.backoff ** qi.attempts)
                    with self.lock:
                        qi.due = time.time() + delay
                        heapq.heappush(self.q, qi)
                else:
                    self._emit_event("dlq", {"id": qi.id, "type": qi.type, "payload": qi.payload, "error": err, "when": time.time()})
                    with self.lock:
                        self.dlq.append({"id": qi.id, "type": qi.type, "payload": qi.payload, "error": err, "when": time.time()})
            else:
                self._emit_event("done", {"id": qi.id, "type": qi.type, "result": res, "when": time.time()})

    def _emit_event(self, kind: str, data: dict):
        try:
            p = self.events_path / f"{kind}_{int(time.time()*1000)}.json"
            p.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
        if self.event_bus:
            try:
                self.event_bus.publish(f"jobs.{kind}", data)
            except Exception:
                pass

    def _execute(self, qi: QItem) -> Tuple[bool, dict, str]:
        try:
            res = self.pm.handle(qi.type, qi.payload, qi.id) or {}
            ok = bool(res.get("ok", True))
            return ok, res, str(res.get("error") if not ok else "")
        except Exception as e:
            return False, {}, str(e)

    def shutdown(self, timeout: float=2.0):
        self.running = False
        with self.lock:
            self.cond.notify_all()
        self.worker.join(timeout=timeout)

    # --- telemetry & persistence ---
    def size(self) -> int:
        with self.lock:
            return len(self.q)
    def get_dlq(self) -> List[dict]:
        with self.lock:
            return list(self.dlq)

    def snapshot(self):
        """Return combined view of active and completed jobs."""
        with self.lock:
            return dict(self._jobs)

    def save_state(self, path="data/state/jobs_state.json"):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            p.write_text(json.dumps(self.snapshot(), indent=2))

    def load_state(self, path="data/state/jobs_state.json"):
        p = Path(path)
        if p.exists():
            with self.lock:
                self._jobs = json.loads(p.read_text())