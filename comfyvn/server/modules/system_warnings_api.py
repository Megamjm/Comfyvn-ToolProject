from __future__ import annotations

from fastapi import APIRouter, Query

from comfyvn.core.warning_bus import warning_bus

router = APIRouter(prefix="/api/system/warnings", tags=["System"])


def _record_to_dict(record):
    return {
        "id": record.id,
        "level": record.level,
        "message": record.message,
        "source": record.source,
        "details": record.details,
        "timestamp": record.timestamp,
    }


@router.get("")
async def list_warnings(limit: int = Query(20, ge=1, le=200)):
    records = warning_bus.list(limit)
    return {"ok": True, "warnings": [_record_to_dict(record) for record in records]}


@router.delete("")
async def clear_warnings():
    warning_bus.clear()
    return {"ok": True}
