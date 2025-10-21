from __future__ import annotations

import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/core/node_manager.py
# ⚙️ ComfyVN Node Manager (v3.0)
# Lightweight registry + heartbeat for distributed compute nodes
# Persists to ./comfyvn/data/nodes_registry.json
# Roles: ["lm", "render", "renpy", "sync", ...]
# [ComfyVN Architect | Server Core Production Chat]

import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional

DATA_DIR = "./comfyvn/data"
REG_FILE = os.path.join(DATA_DIR, "nodes_registry.json")


def _now() -> float:
    return time.time()


def _load() -> Dict[str, Any]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(REG_FILE):
        return {"nodes": {}, "tokens": {}}
    with open(REG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(doc: Dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = REG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REG_FILE)


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:10]


class NodeManager:
    """Minimal node registry with heartbeats and token security."""

    def __init__(self, base_path: str = "", offline_after_sec: int = 35):
        self.base_path = base_path
        self.offline_after = offline_after_sec

    # ---------------- CRUD ----------------
    def register(
        self, payload: Dict[str, Any], ip_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        doc = _load()
        nodes = doc.setdefault("nodes", {})
        tokens = doc.setdefault("tokens", {})

        node_id = payload.get("node_id")
        if not node_id:
            seed = f"{payload.get('name','node')}-{','.join(payload.get('roles',[]))}-{ip_hint or ''}-{_now()}"
            node_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

        token = secrets.token_urlsafe(24)
        tokens[node_id] = token

        nodes[node_id] = {
            "id": node_id,
            "name": payload.get("name") or f"node-{node_id[:4]}",
            "roles": payload.get("roles", []),
            "url": payload.get("url"),
            "ip_hash": _hash_ip(ip_hint or "unknown"),
            "created": _now(),
            "last_seen": _now(),
            "metrics": payload.get("metrics", {}),
            "meta": payload.get("meta", {}),
            "version": payload.get("version"),
        }
        _save(doc)
        return {"ok": True, "node_id": node_id, "token": token, "node": nodes[node_id]}

    def unregister(self, node_id: str) -> Dict[str, Any]:
        doc = _load()
        existed = bool(doc.get("nodes", {}).pop(node_id, None))
        doc.get("tokens", {}).pop(node_id, None)
        _save(doc)
        return {"ok": existed}

    def list(self) -> Dict[str, Any]:
        doc = _load()
        now = _now()
        out = []
        for n in doc.get("nodes", {}).values():
            status = (
                "online"
                if (now - n.get("last_seen", 0)) <= self.offline_after
                else "offline"
            )
            out.append(
                {**n, "status": status, "age": round(now - n.get("created", now), 1)}
            )
        return {"nodes": sorted(out, key=lambda x: x["name"].lower())}

    def ping(
        self, node_id: str, token: str, metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        doc = _load()
        if doc.get("tokens", {}).get(node_id) != token:
            return {"ok": False, "error": "unauthorized"}
        node = doc.get("nodes", {}).get(node_id)
        if not node:
            return {"ok": False, "error": "not_found"}
        node["last_seen"] = _now()
        if metrics:
            node["metrics"] = metrics
        _save(doc)
        return {"ok": True, "node": node}

    # ---------------- Utility ----------------
    def refresh_nodes(self) -> int:
        return len(_load().get("nodes", {}))

    def count_online(self) -> int:
        now = _now()
        nodes = _load().get("nodes", {})
        return len(
            [
                n
                for n in nodes.values()
                if (now - n.get("last_seen", 0)) <= self.offline_after
            ]
        )

    def get(self, node_id: str) -> Dict[str, Any]:
        doc = _load()
        n = doc.get("nodes", {}).get(node_id)
        if not n:
            return {}
        status = (
            "online"
            if (_now() - n.get("last_seen", 0)) <= self.offline_after
            else "offline"
        )
        return {**n, "status": status}

    def update_roles(
        self, node_id: str, token: str, roles: List[str]
    ) -> Dict[str, Any]:
        doc = _load()
        if doc.get("tokens", {}).get(node_id) != token:
            return {"ok": False, "error": "unauthorized"}
        node = doc.get("nodes", {}).get(node_id)
        if not node:
            return {"ok": False, "error": "not_found"}
        node["roles"] = roles or []
        _save(doc)
        return {"ok": True, "node": node}

    def set_token(
        self, node_id: str, old_token: str, new_token: Optional[str] = None
    ) -> Dict[str, Any]:
        doc = _load()
        if doc.get("tokens", {}).get(node_id) != old_token:
            return {"ok": False, "error": "unauthorized"}
        doc["tokens"][node_id] = new_token or secrets.token_urlsafe(24)
        _save(doc)
        return {"ok": True, "token": doc["tokens"][node_id]}
