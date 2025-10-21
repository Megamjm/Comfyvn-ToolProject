from __future__ import annotations

from fastapi import APIRouter, Response
from PySide6.QtGui import QAction


def SchedulerRouter(scheduler=None):
    r = APIRouter()

    @r.get("/health")
    async def health():
        return {"ok": True, "scheduler_attached": bool(scheduler)}

    @r.get("/ics")
    async def ics():
        return Response(
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//ComfyVN//EN\nEND:VCALENDAR\n",
            media_type="text/calendar",
        )

    return r
