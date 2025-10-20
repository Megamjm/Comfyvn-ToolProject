from PySide6.QtGui import QAction

from fastapi import APIRouter
router = APIRouter(prefix="/market", tags=["market"])

@router.get("/list")
def list_assets():
    return {"ok":True,"items":[
        {"id":"bg_city","type":"background","license":"CC0"},
        {"id":"sfx_click","type":"sound","license":"CC0"},
        {"id":"char_base_female","type":"sprite","license":"CC-BY"}
    ]}