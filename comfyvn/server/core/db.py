from __future__ import annotations
from PySide6.QtGui import QAction
import os, json, time
from typing import Generator, Optional, Any, Dict
from pathlib import Path
from sqlalchemy import create_engine, Integer, String, Text, Boolean, Float
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.exc import OperationalError

DB_URL = os.getenv("DB_URL", "")  # e.g., postgresql+psycopg2://user:pass@host/db or sqlite:///./data/app.db
ECHO = bool(int(os.getenv("DB_ECHO","0")))

class Base(DeclarativeBase):
    pass

class SceneRow(Base):
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    data: Mapped[str] = mapped_column(Text)  # JSON string
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())
    updated: Mapped[float] = mapped_column(Float, default=lambda: time.time())

class CharacterRow(Base):
    __tablename__ = "characters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    data: Mapped[str] = mapped_column(Text)  # JSON string
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())
    updated: Mapped[float] = mapped_column(Float, default=lambda: time.time())

class TokenRow(Base):
    __tablename__ = "tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    scopes: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())



class OrgRow(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())

class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    pass_hash: Mapped[str] = mapped_column(String(255), default="")
    default_org: Mapped[str] = mapped_column(String(64), default="")
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())
    last_login: Mapped[float] = mapped_column(Float, default=0.0)

class MembershipRow(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64), default="viewer")

class ApiTokenRow(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    scopes: Mapped[str] = mapped_column(Text, default="[]")
    hash: Mapped[str] = mapped_column(String(64))  # sha256 of raw token
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())
    expires: Mapped[float] = mapped_column(Float, default=0.0)
    last_used: Mapped[float] = mapped_column(Float, default=0.0)
    revoked: Mapped[int] = mapped_column(Integer, default=0)

class ArtifactRow(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    art_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    scene_id: Mapped[str] = mapped_column(String(255), index=True, default="")
    kind: Mapped[str] = mapped_column(String(64), index=True, default="file")
    path: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created: Mapped[float] = mapped_column(Float, default=lambda: time.time())

class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    started: Mapped[float] = mapped_column(Float, default=0.0)
    finished: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    outputs: Mapped[str] = mapped_column(Text, default="{}")

_engine = None
SessionLocal = None

def _ensure_engine():
    global _engine, SessionLocal
    if _engine is not None: return _engine
    url = DB_URL.strip()
    if not url:
        # default to sqlite under data for convenience if DB_URL not set but module used directly
        url = "sqlite:///./data/app.db"
    from sqlalchemy.pool import StaticPool
    if url.startswith("sqlite"):
        _engine = create_engine(url, echo=ECHO, future=True)
    else:
        _engine = create_engine(url, echo=ECHO, future=True, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine

def init_db() -> bool:
    try:
        eng = _ensure_engine()
        Base.metadata.create_all(eng)
        return True
    except OperationalError:
        return False
    except Exception:
        return False

def get_db() -> Generator:
    if SessionLocal is None: _ensure_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- helpers ---
def is_enabled() -> bool:
    return bool(DB_URL.strip())

def as_json_str(obj: Any) -> str:
    import json as _json
    return _json.dumps(obj, ensure_ascii=False)

def from_json_str(s: str) -> Any:
    import json as _json
    try: return _json.loads(s or "{}")
    except Exception: return {}