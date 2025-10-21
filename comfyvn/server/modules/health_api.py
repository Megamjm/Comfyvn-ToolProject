# comfyvn/server/modules/health_api.py
from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/system/health")
def system_health():
    return {"ok": True, "service": "system"}


@router.get("/jobs/health")
def jobs_health():
    return {"ok": True, "service": "jobs"}


@router.get("/render/health")
def render_health():
    return {"ok": True, "service": "render"}


@router.get("/meta/info")
def meta_info():
    return {"ok": True, "name": "ComfyVN", "version": "6.0.0"}


@router.get("/meta/checks")
def meta_checks():
    return {"ok": True, "checks": ["routes", "deps", "storage"]}
