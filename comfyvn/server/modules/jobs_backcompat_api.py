# comfyvn/server/modules/jobs_backcompat_api.py
from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.post("/enqueue-test")
def enqueue_test():
    return {"ok": True, "enqueue_ok": True, "id": "testjob"}
