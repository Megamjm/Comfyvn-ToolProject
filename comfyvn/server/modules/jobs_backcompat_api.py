from PySide6.QtGui import QAction

# comfyvn/server/modules/jobs_backcompat_api.py
from fastapi import APIRouter
router = APIRouter()

@router.post("/enqueue-test")
def enqueue_test():
    return {"ok": True, "enqueue_ok": True, "id": "testjob"}