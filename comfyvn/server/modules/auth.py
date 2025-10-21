"""Authentication helpers and scope checks for ComfyVN APIs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import Depends, HTTPException, Request
try:  # pragma: no cover - optional dependency
    from passlib.hash import bcrypt
except Exception:  # pragma: no cover - lightweight fallback
    class _FallbackBcrypt:
        @staticmethod
        def hash(value: str) -> str:
            return hashlib.sha256(value.encode("utf-8")).hexdigest()

    bcrypt = _FallbackBcrypt()  # type: ignore
from sqlalchemy.orm import Session

from comfyvn.server.core.db import (
    ApiTokenRow,
    MembershipRow,
    OrgRow,
    UserRow,
    get_db,
    init_db,
    is_enabled,
)

# Role -> scopes mapping used for coarse-grained authorisation.
ROLE_SCOPES: Dict[str, List[str]] = {
    "admin": ["*"],
    "editor": [
        "content.*",
        "io.*",
        "search.*",
        "jobs.*",
        "scheduler.*",
        "artifacts.*",
        "lineage.*",
        "assets.*",
        "mass-edit.*",
        "db.*",
    ],
    "viewer": ["search.read", "content.read", "artifacts.read", "lineage.read"],
}


def _normalize_scopes(scopes: List[str]) -> Set[str]:
    out: Set[str] = set()
    for scope in scopes or []:
        scope = str(scope).strip()
        if not scope:
            continue
        out.add(scope)
    return out


def _scopes_from_role(role: str) -> Set[str]:
    base = ROLE_SCOPES.get(role or "viewer", [])
    return _normalize_scopes(base)


def _match(scope: str, have: Set[str]) -> bool:
    if "*" in have:
        return True
    if scope in have:
        return True
    parts = scope.split(".")
    for length in range(len(parts), 0, -1):
        prefix = ".".join(parts[:length]) + ".*"
        if prefix in have:
            return True
    return False


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_scope(required: List[str] | str, cost: int = 1):
    """FastAPI dependency that enforces token scopes."""

    required_scopes = required if isinstance(required, list) else [required]

    async def _dependency(request: Request, db: Session = Depends(get_db)) -> bool:
        # Admin override via env API_TOKEN for legacy integrations.
        auth_header = request.headers.get("Authorization", "")
        legacy_token = os.getenv("API_TOKEN", "")
        if legacy_token:
            if not auth_header:
                return True
            if auth_header == legacy_token or auth_header == f"Bearer {legacy_token}":
                return True

        # Bearer token lookup.
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        raw_token = auth_header.split(" ", 1)[1].strip()
        token_hash = _token_hash(raw_token)

        init_db()
        token = db.query(ApiTokenRow).filter_by(hash=token_hash, revoked=0).first()

        try:
            from comfyvn.server.core.ratelimit import enforce as _rl_enforce  # type: ignore

            if token:
                _rl_enforce(db, token, cost=cost)
        except Exception:  # pragma: no cover - best-effort enforcement
            pass

        if not token:
            raise HTTPException(status_code=401, detail="invalid token")
        if token.expires and time.time() > token.expires:
            raise HTTPException(status_code=401, detail="token expired")

        membership = (
            db.query(MembershipRow)
            .filter_by(user_id=token.user_id, org_id=token.org_id)
            .first()
        )
        role_scopes = _scopes_from_role(membership.role if membership else "viewer")
        token_scopes = set(json.loads(token.scopes or "[]"))
        available_scopes = token_scopes.union(role_scopes)

        for scope in required_scopes:
            if not _match(scope, available_scopes):
                raise HTTPException(status_code=403, detail=f"scope {scope} required")

        token.last_used = time.time()
        db.commit()
        return True

    return _dependency


# Helper for auth API

def init_first_admin(db: Session) -> Optional[Dict[str, Any]]:
    init_db()
    existing = db.query(UserRow).first()
    if existing:
        return None

    org_id = "default"
    org = OrgRow(org_id=org_id, name="Default")
    db.add(org)
    db.commit()

    user = UserRow(
        user_id=secrets.token_hex(8),
        email="admin@example.com",
        name="Admin",
        pass_hash=bcrypt.hash("admin"),
        default_org=org_id,
        created=time.time(),
    )
    db.add(user)
    db.commit()

    membership = MembershipRow(user_id=user.user_id, org_id=org_id, role="admin")
    db.add(membership)
    db.commit()

    raw_token = "admintoken"
    token = ApiTokenRow(
        token_id=secrets.token_hex(8),
        user_id=user.user_id,
        org_id=org_id,
        name="bootstrap",
        scopes=json.dumps(["*"]),
        hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        created=time.time(),
    )
    db.add(token)
    db.commit()

    return {"email": user.email, "password": "admin", "token": raw_token}


__all__ = [
    "ROLE_SCOPES",
    "require_scope",
    "init_first_admin",
]
