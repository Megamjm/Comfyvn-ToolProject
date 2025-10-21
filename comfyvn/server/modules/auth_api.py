from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from passlib.hash import bcrypt
from PySide6.QtGui import QAction
from sqlalchemy.orm import Session

from comfyvn.server.core.db import (ApiTokenRow, MembershipRow, OrgRow,
                                    UserRow, get_db, init_db, is_enabled)
from comfyvn.server.modules.auth import (_scopes_from_role, _token_hash,
                                         init_first_admin, require_scope)

router = APIRouter()


@router.get("/bootstrap")
async def bootstrap(db: Session = Depends(get_db)):
    init_db()
    info = init_first_admin(db)
    return {"ok": True, "bootstrap": info or {}}


@router.post("/register")
async def register(body: Dict[str, Any], db: Session = Depends(get_db)):
    init_db()
    email = str(body.get("email") or "").lower().strip()
    password = str(body.get("password") or "")
    name = str(body.get("name") or "")
    if not email or not password:
        raise HTTPException(400, "email and password required")
    if db.query(UserRow).filter_by(email=email).first():
        raise HTTPException(400, "email exists")
    # ensure default org
    org_id = "default"
    org = db.query(OrgRow).filter_by(org_id=org_id).first()
    if not org:
        org = OrgRow(org_id=org_id, name="Default")
        db.add(org)
        db.commit()
    uid = secrets.token_hex(8)
    usr = UserRow(
        user_id=uid,
        email=email,
        name=name,
        pass_hash=bcrypt.hash(password),
        default_org=org_id,
        created=time.time(),
    )
    db.add(usr)
    db.commit()
    # first non-bootstrap user becomes editor
    role = "editor" if db.query(UserRow).count() > 1 else "admin"
    mem = MembershipRow(user_id=uid, org_id=org_id, role=role)
    db.add(mem)
    db.commit()
    return {"ok": True, "user_id": uid, "role": role}


@router.post("/login")
async def login(body: Dict[str, Any], db: Session = Depends(get_db)):
    email = str(body.get("email") or "").lower().strip()
    password = str(body.get("password") or "")
    u = db.query(UserRow).filter_by(email=email).first()
    if not u or not bcrypt.verify(password, u.pass_hash):
        raise HTTPException(401, "invalid credentials")
    # issue a session token (API token)
    mem = (
        db.query(MembershipRow)
        .filter_by(user_id=u.user_id, org_id=u.default_org)
        .first()
    )
    scopes = list(_scopes_from_role(mem.role if mem else "viewer"))
    raw = "atk_" + secrets.token_urlsafe(24)
    tok = ApiTokenRow(
        token_id=secrets.token_hex(8),
        user_id=u.user_id,
        org_id=u.default_org,
        name="session",
        scopes=json.dumps(scopes),
        hash=_token_hash(raw),
        created=time.time(),
        expires=time.time() + 7 * 24 * 3600,
    )
    db.add(tok)
    db.commit()
    u.last_login = time.time()
    db.commit()
    return {"ok": True, "token": raw, "org_id": u.default_org, "scopes": scopes}


@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer")
    raw = auth.split(" ", 1)[1].strip()
    h = _token_hash(raw)
    tok = db.query(ApiTokenRow).filter_by(hash=h, revoked=0).first()
    if not tok:
        raise HTTPException(401, "invalid token")
    u = db.query(UserRow).filter_by(user_id=tok.user_id).first()
    mem = (
        db.query(MembershipRow)
        .filter_by(user_id=tok.user_id, org_id=tok.org_id)
        .first()
    )
    return {
        "ok": True,
        "user": {"email": u.email, "name": u.name, "user_id": u.user_id},
        "org_id": tok.org_id,
        "role": mem.role if mem else "viewer",
        "scopes": json.loads(tok.scopes or "[]"),
    }


@router.post("/tokens/create")
async def tokens_create(
    body: Dict[str, Any],
    _: bool = Depends(require_scope(["*"])),
    db: Session = Depends(get_db),
    request: Request = None,
):
    # Only admins via '*' can mint full-scope tokens. Editors can mint limited scopes they already possess.
    name = str(body.get("name") or "token")
    scopes = body.get("scopes") or ["*"]
    days = int(body.get("days") or 30)
    # issuer is token owner from header
    auth = request.headers.get("Authorization", "")
    raw = auth.split(" ", 1)[1].strip()
    h = _token_hash(raw)
    parent = db.query(ApiTokenRow).filter_by(hash=h, revoked=0).first()
    if not parent:
        raise HTTPException(401, "invalid token")
    user_id = parent.user_id
    org_id = parent.org_id
    raw_new = "atk_" + secrets.token_urlsafe(24)
    tok = ApiTokenRow(
        token_id=secrets.token_hex(8),
        user_id=user_id,
        org_id=org_id,
        name=name,
        scopes=json.dumps(scopes),
        hash=_token_hash(raw_new),
        created=time.time(),
        expires=(time.time() + days * 24 * 3600),
    )
    db.add(tok)
    db.commit()
    return {"ok": True, "token": raw_new, "expires": tok.expires}


@router.get("/tokens/list")
async def tokens_list(
    _: bool = Depends(require_scope(["content.read"])),
    db: Session = Depends(get_db),
    request: Request = None,
):
    auth = request.headers.get("Authorization", "")
    raw = auth.split(" ", 1)[1].strip()
    h = _token_hash(raw)
    parent = db.query(ApiTokenRow).filter_by(hash=h, revoked=0).first()
    items = []
    for t in (
        db.query(ApiTokenRow)
        .filter_by(user_id=parent.user_id, org_id=parent.org_id)
        .all()
    ):
        items.append(
            {
                "token_id": t.token_id,
                "name": t.name,
                "scopes": json.loads(t.scopes or "[]"),
                "created": t.created,
                "expires": t.expires,
                "revoked": bool(t.revoked),
            }
        )
    return {"ok": True, "items": items}


@router.post("/tokens/revoke")
async def tokens_revoke(
    body: Dict[str, Any],
    _: bool = Depends(require_scope(["content.write"])),
    db: Session = Depends(get_db),
    request: Request = None,
):
    tid = str(body.get("token_id") or "")
    if not tid:
        raise HTTPException(400, "token_id required")
    t = db.query(ApiTokenRow).filter_by(token_id=tid).first()
    if not t:
        raise HTTPException(404, "not found")
    t.revoked = 1
    db.commit()
    return {"ok": True}
