from __future__ import annotations
from PySide6.QtGui import QAction
import json, time, threading, uuid, os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from croniter import croniter
from zoneinfo import ZoneInfo
import random, datetime as _dt

SCHED_PATH = Path("./data/scheduler.json"); SCHED_PATH.parent.mkdir(parents=True, exist_ok=True)

def _now_ts() -> float: return time.time()

def _load() -> Dict[str, Any]:
    if SCHED_PATH.exists():
        try: return json.loads(SCHED_PATH.read_text(encoding="utf-8"))
        except Exception: return {"items": []}
    return {"items": []}

def _save(db: Dict[str, Any]):
    SCHED_PATH.write_text(json.dumps(db, indent=2), encoding="utf-8")

class Enqueuer:
    def __init__(self, jm, redis_queue, default_retries: int = 0):
        self.jm = jm; self.rq = redis_queue; self.default_retries = default_retries
    def enqueue(self, typ: str, payload: Dict[str, Any], retries: Optional[int] = None) -> str:
        r = retries if retries is not None else self.default_retries
        if self.rq: return self.rq.enqueue(typ, payload, retries=r)
        return self.jm.enqueue(typ, payload, retries=r)

class Scheduler:
    def __init__(self, enq: Enqueuer):
        self.enq = enq
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def list(self) -> List[Dict[str, Any]]:
        return list(_load().get("items", []))

    def _save_items(self, items: List[Dict[str, Any]]):
        _save({"items": items})

    def add(self, typ: str, payload: Dict[str, Any], cron: str, *, enabled: bool = True, name: Optional[str] = None, retries: int = 0) -> Dict[str, Any]:
        it = {
            "id": uuid.uuid4().hex[:12],
            "name": name or f"{typ}_{int(_now_ts())}",
            "type": typ,
            "payload": payload,
            "cron": cron,
            "enabled": bool(enabled),
            "retries": int(retries),
            "tz": str((payload or {}).get("tz") or "UTC"),
            "jitter_sec": int((payload or {}).get("jitter_sec") or 0),
            "misfire_policy": str((payload or {}).get("misfire_policy") or "fire_now"),
            "misfire_grace_sec": int((payload or {}).get("misfire_grace_sec") or 300),
            "concurrency": str((payload or {}).get("concurrency") or "overlap"),
            "lock_ttl_sec": int((payload or {}).get("lock_ttl_sec") or 0),
            "blackout": (payload or {}).get("blackout") or [],
            "lock_until": 0.0,
            "last_run": None,
            "next_run": None,
            "created": _now_ts()
        }
        # compute first next_run
        tz = ZoneInfo(it.get("tz") or "UTC")
        base = _dt.datetime.fromtimestamp(_now_ts(), tz=tz)
        try:
            nxt = croniter(cron, base).get_next(_dt.datetime)
            j = int(it.get("jitter_sec") or 0)
            if j>0:
                nxt = nxt + _dt.timedelta(seconds=random.randint(0, j))
            it["next_run"] = float(nxt.timestamp())
        except Exception:
            raise ValueError("invalid cron expression")
        with self.lock:
            db = _load(); items = db.get("items", []); items.append(it); self._save_items(items)
        return it

    def update(self, sid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            items = self.list()
            for it in items:
                if it["id"] == sid:
                    it.update({k: v for k, v in patch.items() if k in {"name","cron","payload","type","enabled","retries"}})
                    # recompute next_run if cron changed
                    if "cron" in patch:
                        tz = ZoneInfo(it.get("tz") or "UTC")
                        base = _dt.datetime.fromtimestamp(_now_ts(), tz=tz)
                        nxt = croniter(it["cron"], base).get_next(_dt.datetime)
                        j = int(it.get("jitter_sec") or 0)
                        if j>0:
                            nxt = nxt + _dt.timedelta(seconds=random.randint(0, j))
                        it["next_run"] = float(nxt.timestamp())
                    self._save_items(items)
                    return it
        raise KeyError("schedule not found")

    def remove(self, sid: str) -> bool:
        with self.lock:
            items = self.list()
            nitems = [it for it in items if it["id"] != sid]
            self._save_items(nitems)
        return len(nitems) != len(items)

    def run_now(self, sid: str) -> Optional[str]:
        with self.lock:
            for it in self.list():
                if it["id"] == sid:
                    jid = self.enq.enqueue(it["type"], it["payload"], retries=it.get("retries", 0))
                    it["last_run"] = _now_ts()
                    # keep next_run as is
                    db = _load(); items = db.get("items", [])
                    for jt in items:
                        if jt["id"] == sid:
                            jt.update({"last_run": it["last_run"]})
                    _save({"items": items})
                    return jid
        return None

    
    def _in_blackout(self, it, now_ts: float) -> bool:
        try:
            tz = ZoneInfo(it.get("tz") or "UTC")
            now = _dt.datetime.fromtimestamp(now_ts, tz=tz)
            rules = it.get("blackout") or []
            dow_map = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
            for r in rules:
                dow = (r.get("dow") or "*").lower()
                if dow != "*" and dow_map.get(dow, -1) != now.weekday(): continue
                s = r.get("start","00:00"); e = r.get("end","23:59")
                hs, ms = [int(x) for x in s.split(":")]; he, me = [int(x) for x in e.split(":")]
                st = now.replace(hour=hs, minute=ms, second=0, microsecond=0)
                en = now.replace(hour=he, minute=me, second=59, microsecond=0)
                if st <= now <= en: return True
        except Exception:
            return False
        return False

    def _tick(self):
        while not self._stop.is_set():
            try:
                now = _now_ts()
                changed = False
                items = self.list()
                for it in items:
                    if not it.get("enabled", True): continue
                    nr = float(it.get("next_run") or 0)
                    if nr and now + 0.5 >= nr:
                        # blackout check
                        if self._in_blackout(it, now):
                            # compute next and skip
                            try:
                                tz = ZoneInfo(it.get("tz") or "UTC")
                                base = _dt.datetime.fromtimestamp(nr, tz=tz)
                                nxt = croniter(it["cron"], base).get_next(_dt.datetime)
                                j = int(it.get("jitter_sec") or 0)
                                if j>0: nxt = nxt + _dt.timedelta(seconds=random.randint(0, j))
                                it["next_run"] = float(nxt.timestamp())
                            except Exception:
                                it["enabled"] = False
                            changed = True
                            continue
                        # misfire handling
                        grace = int(it.get("misfire_grace_sec") or 300)
                        policy = (it.get("misfire_policy") or "fire_now")
                        late = now - nr
                        should_fire = True
                        if late > grace:
                            if policy == "skip":
                                should_fire = False
                            elif policy == "queue":
                                should_fire = True
                            else:  # fire_now
                                should_fire = True
                        # concurrency policy via lock
                        conc = (it.get("concurrency") or "overlap")
                        lock_until = float(it.get("lock_until") or 0)
                        if conc in {"skip","queue"} and lock_until > now:
                            # reschedule if queue policy else skip to next
                            if conc == "queue": should_fire = False
                            else: should_fire = False
                        if should_fire:
                            jid = self.enq.enqueue(it["type"], it["payload"], retries=it.get("retries", 0))
                            it["last_run"] = now
                            # set lock if configured
                            lttl = int(it.get("lock_ttl_sec") or 0)
                            if lttl > 0 and conc in {"skip","queue"}: it["lock_until"] = now + lttl
                        # compute next
                        try:
                            tz = ZoneInfo(it.get("tz") or "UTC")
                            base = _dt.datetime.fromtimestamp(nr, tz=tz)
                            nxt = croniter(it["cron"], base).get_next(_dt.datetime)
                            j = int(it.get("jitter_sec") or 0)
                            if j>0: nxt = nxt + _dt.timedelta(seconds=random.randint(0, j))
                            it["next_run"] = float(nxt.timestamp())
                        except Exception:
                            it["enabled"] = False
                        changed = True
                if changed:
                    self._save_items(items)
            except Exception:
                pass
            self._stop.wait(1.0)

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop.clear()
        self._thread = threading.Thread(target=self._tick, daemon=True); self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(timeout=2)