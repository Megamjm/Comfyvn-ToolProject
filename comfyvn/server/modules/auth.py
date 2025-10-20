from __future__ import annotations
from PySide6.QtGui import QAction
import os, time, json, secrets, hashlib
from typing import Dict, Any, List, Optional, Set
from fastapi import Depends, HTTPException
from fastapi import Request
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from comfyvn.server.core.db import get_db, init_db, is_enabled, UserRow, OrgRow, MembershipRow, ApiTokenRow

# Role -> scopes
ROLE_SCOPES = {
    "admin": ["*"],
    "editor": ["content.*","io.*","search.*","jobs.*","scheduler.*","artifacts.*","lineage.*","assets.*","mass-edit.*","db.*"],
    "viewer": ["search.read","content.read","artifacts.read","lineage.read"]
}

def _normalize_scopes(scopes: List[str]) -> Set[str]:
    out: Set[str] = set()
    for s in scopes or []:
        s = str(s).strip()
        if not s: continue
        out.add(s)
    return out

def _scopes_from_role(role: str) -> Set[str]:
    base = ROLE_SCOPES.get(role or "viewer", [])
    return _normalize_scopes(base)

def _match(scope: str, have: Set[str]) -> bool:
    if "*" in have: return True
    if scope in have: return True
    parts = scope.split(".")
    for i in range(len(parts), 0, -1):
        pref = ".".join(parts[:i]) + ".*"
        if pref in have: return True
    return False

def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def require_scope(required: List[str] | str, cost: int = 1):
    req = required if isinstance(required, list) else [required]
    async def dep(request: Request, db: Session = Depends(get_db)):
        # Admin override via env API_TOKEN for legacy
        auth = request.headers.get("Authorization","")
        legacy = os.getenv("API_TOKEN","")
        if legacy and (auth == legacy or auth == f"Bearer {legacy}"):
            return True
        # Bearer token lookup
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        raw = auth.split(" ",1)[1].strip()
        h = _token_hash(raw)
        init_db()
        tok = db.query(ApiTokenRow).filter_by(hash=h, revoked=0).first()
        try:
            from comfyvn.server.core.ratelimit import enforce as _rl_enforce
            if tok: _rl_enforce(db, tok, cost=cost)
        except Exception:
            pass
        if not tok:
            raise HTTPException(401, "invalid token")
        if tok.expires and time.time() > tok.expires:
            raise HTTPException(401, "token expired")
        # scopes check: token scopes ∩ role scopes must cover required
        # role scopes
        mem = db.query(MembershipRow).filter_by(user_id=tok.user_id, org_id=tok.org_id).first()
        role_sc = _scopes_from_role(mem.role if mem else "viewer")
        tok_sc = set(json.loads(tok.scopes or "[]"))
        have = set()
        for s in tok_sc.union(role_sc):
            have.add(s)
        for r in req:
            if not _match(r, have):
                raise HTTPException(403, f"scope {r} required")
        tok.last_used = time.time(); db.commit()
        return True
    return dep

# Helper for auth API
def init_first_admin(db: Session) -> Optional[Dict[str,Any]]:
    init_db()
    u = db.query(UserRow).first()
    if u: return None
    # bootstrap
    org_id = "default"
    org = OrgRow(org_id=org_id, name="Default")
    db.add(org); db.commit()
    usr = UserRow(user_id=secrets.token_hex(8), email="admin@example.com", name="Admin", pass_hash=bcrypt.hash("admin"), default_org=org_id, created=time.time())
    db.add(usr); db.commit()
    mem = MembershipRow(user_id=usr.user_id, org_id=org_id, role="admin")
    db.add(mem); db.commit()
    # create bootstrap token
    raw = "admintoken"
    tok = ApiTokenRow(token_id=secrets.token_hex(8), user_id=usr.user_id, org_id=org_id, name="bootstrap", scopes=json.dumps(["*"]), hash=hashlib.sha256(raw.encode()).hexdigest(), created=time.time())
    db.add(tok); db.commit()
    return {"email": usr.email, "password": "admin", "token": raw}