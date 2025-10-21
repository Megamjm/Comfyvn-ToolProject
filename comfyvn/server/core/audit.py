from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Request, Response
from PySide6.QtGui import QAction
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from comfyvn.server.core.db import (ApiTokenRow, MembershipRow, UserRow,
                                    get_db, init_db)

AUDIT_DIR = Path("./data/audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
REDACT_KEYS = {"password", "pass", "token", "secret", "api_key", "authorization"}


def _redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in REDACT_KEYS:
                out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _file_for_ts(ts: float) -> Path:
    t = time.gmtime(ts)
    return AUDIT_DIR / f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}.jsonl"


def _hash(prev: str, record: Dict[str, Any], secret: str | None) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    base = (prev or "").encode("utf-8") + b"|" + payload
    if secret:
        return hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hashlib.sha256(base).hexdigest()


class AuditLogger:
    def __init__(self, secret: str | None = None):
        self.secret = secret or os.getenv("AUDIT_HMAC_SECRET", "")
        self.prev_hash = ""

    def write(self, rec: Dict[str, Any]):
        ts = rec.get("ts") or time.time()
        path = _file_for_ts(ts)
        path.parent.mkdir(parents=True, exist_ok=True)
        # chain per-file: read last line to get prev
        if path.exists():
            try:
                *_, last = path.read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()
                prev = json.loads(last).get("hash", "")
            except Exception:
                prev = ""
        else:
            prev = ""
        rec["hash"] = _hash(prev, rec, self.secret)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = AuditLogger()

    async def dispatch(self, request: Request, call_next):
        ts = time.time()
        # headers
        hdr = {
            k.lower(): (v if k.lower() != "authorization" else "***")
            for k, v in request.headers.items()
        }
        # body (best effort)
        try:
            body_bytes = await request.body()
            try:
                body = json.loads(body_bytes.decode("utf-8"))
                body = _redact(body)
            except Exception:
                body = None
        except Exception:
            body = None
        # actor from DB token or legacy env
        actor = {"mode": "anonymous"}
        try:
            auth = request.headers.get("Authorization", "")
            legacy = os.getenv("API_TOKEN", "")
            if legacy and (auth == legacy or auth == f"Bearer {legacy}"):
                actor = {
                    "mode": "legacy",
                    "user": "legacy-admin",
                    "org": "default",
                    "role": "admin",
                }
            elif auth.lower().startswith("bearer "):
                raw = auth.split(" ", 1)[1].strip()
                h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                init_db()
                for db in get_db():
                    tok = db.query(ApiTokenRow).filter_by(hash=h, revoked=0).first()
                    if tok:
                        u = db.query(UserRow).filter_by(user_id=tok.user_id).first()
                        mem = (
                            db.query(MembershipRow)
                            .filter_by(user_id=tok.user_id, org_id=tok.org_id)
                            .first()
                        )
                        actor = {
                            "mode": "token",
                            "user": u.email if u else tok.user_id,
                            "user_id": tok.user_id,
                            "org": tok.org_id,
                            "role": mem.role if mem else "viewer",
                            "token_id": tok.token_id,
                        }
                    break
        except Exception:
            pass
        # call downstream
        resp: Response = await call_next(request)
        rec = {
            "ts": ts,
            "ip": request.client.host if request.client else "",
            "host": request.headers.get("host", ""),
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "status": resp.status_code,
            "length": int(resp.headers.get("content-length") or 0),
            "headers": hdr,
            "body": body,
            "actor": actor,
            "service": "comfyvn",
            "node": socket.gethostname(),
        }
        try:
            self.logger.write(rec)
        except Exception:
            pass
        return resp


def export_range(start_ts: float, end_ts: float) -> str:
    # concatenate files within range
    out = []
    t = start_ts
    day = 24 * 3600
    cur = int(start_ts // day) * day
    while cur <= end_ts + day:
        p = _file_for_ts(cur)
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    rec = json.loads(line)
                    if start_ts <= float(rec.get("ts", 0)) <= end_ts:
                        out.append(line)
                except Exception:
                    continue
        cur += day
    return "\n".join(out)


def verify_range(
    start_ts: float, end_ts: float, secret: str | None = None
) -> Dict[str, Any]:
    secret = secret or os.getenv("AUDIT_HMAC_SECRET", "")
    problems = []
    prev = ""
    t = start_ts
    day = 24 * 3600
    cur = int(start_ts // day) * day
    while cur <= end_ts + day:
        p = _file_for_ts(cur)
        if p.exists():
            for line_no, line in enumerate(
                p.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
            ):
                try:
                    rec = json.loads(line)
                    ts = float(rec.get("ts", 0))
                    if not (start_ts <= ts <= end_ts):
                        continue
                    expected = rec.get("hash", "")
                    computed = (
                        hmac.new(
                            secret.encode("utf-8"),
                            (
                                prev
                                + "|"
                                + json.dumps(
                                    {k: v for k, v in rec.items() if k != "hash"},
                                    sort_keys=True,
                                    separators=(",", ":"),
                                )
                            ).encode("utf-8"),
                            hashlib.sha256,
                        ).hexdigest()
                        if secret
                        else hashlib.sha256(
                            (
                                prev
                                + "|"
                                + json.dumps(
                                    {k: v for k, v in rec.items() if k != "hash"},
                                    sort_keys=True,
                                    separators=(",", ":"),
                                )
                            ).encode("utf-8")
                        ).hexdigest()
                    )
                    if expected != computed:
                        problems.append(
                            {"file": p.name, "line": line_no, "error": "hash mismatch"}
                        )
                    prev = expected
                except Exception as e:
                    problems.append({"file": p.name, "line": line_no, "error": "parse"})
        cur += day
    return {"ok": len(problems) == 0, "problems": problems}
