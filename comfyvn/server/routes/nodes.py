# comfyvn/server/routes/nodes.py
# ⚙️ Node Management API — REST endpoints for distributed compute nodes
# [ComfyVN Architect | Server Core Production Chat]

from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from comfyvn.core.node_manager import NodeManager

router = APIRouter(prefix="/nodes", tags=["Nodes"])

# Initialize NodeManager
node_manager = NodeManager()


# ---------------- Register ----------------
@router.post("/register")
async def nodes_register(request: Request):
    """Register a new node with optional roles, url, and metrics."""
    payload = await request.json()
    ip = request.client.host if request.client else "unknown"
    res = node_manager.register(payload, ip_hint=ip)
    return {"ok": True, "registered": res}


# ---------------- Ping ----------------
@router.post("/ping")
async def nodes_ping(request: Request):
    """Update node heartbeat and optional metrics."""
    payload = await request.json()
    node_id = payload.get("node_id")
    token = payload.get("token")
    metrics = payload.get("metrics", {})
    if not node_id or not token:
        raise HTTPException(status_code=400, detail="Missing node_id/token")
    res = node_manager.ping(node_id, token, metrics)
    if not res.get("ok"):
        raise HTTPException(status_code=403, detail=res.get("error", "unauthorized"))
    return res


# ---------------- List ----------------
@router.get("/list")
async def nodes_list():
    """Return all registered nodes with status."""
    return node_manager.list()


# ---------------- Unregister ----------------
@router.post("/unregister")
async def nodes_unregister(payload: dict):
    """Remove a node from registry."""
    node_id = payload.get("node_id")
    if not node_id:
        raise HTTPException(status_code=400, detail="Missing node_id")
    res = node_manager.unregister(node_id)
    return res


# ---------------- Update Roles ----------------
@router.post("/update_roles")
async def nodes_update_roles(payload: dict):
    """Change roles for a given node."""
    node_id = payload.get("node_id")
    token = payload.get("token")
    roles = payload.get("roles", [])
    if not node_id or not token:
        raise HTTPException(status_code=400, detail="Missing node_id/token")
    res = node_manager.update_roles(node_id, token, roles)
    if not res.get("ok"):
        raise HTTPException(status_code=403, detail=res.get("error", "unauthorized"))
    return res


# ---------------- Set Token ----------------
@router.post("/set_token")
async def nodes_set_token(payload: dict):
    """Rotate or replace node access token."""
    node_id = payload.get("node_id")
    old_token = payload.get("old_token")
    new_token = payload.get("new_token")
    if not node_id or not old_token:
        raise HTTPException(status_code=400, detail="Missing node_id/old_token")
    res = node_manager.set_token(node_id, old_token, new_token)
    if not res.get("ok"):
        raise HTTPException(status_code=403, detail=res.get("error", "unauthorized"))
    return res
