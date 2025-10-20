from PySide6.QtGui import QAction
from fastapi import APIRouter
router = APIRouter()

@router.post("/enqueue-test")
def enqueue_test():
    return {"ok": True, "enqueue_ok": True}