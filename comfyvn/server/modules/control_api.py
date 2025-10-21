from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter(tags=["Player Control"])


def _persona_manager(request: Request):
    manager = getattr(request.app.state, "persona", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="persona manager unavailable")
    return manager


@router.get("/who")
def who(request: Request) -> Dict[str, Any]:
    manager = _persona_manager(request)
    state = manager.get_active_selection()
    return {"ok": True, "state": state}


@router.post("/swap")
def swap(request: Request, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    manager = _persona_manager(request)
    persona_id = body.get("persona") or body.get("persona_id")
    character_id = body.get("character") or body.get("character_id") or body.get("name")
    reason = body.get("reason") or "manual"
    mode = body.get("mode")

    try:
        if persona_id:
            state = manager.set_active_persona(
                persona_id,
                character_id=character_id,
                mode=mode,
                reason=reason,
            )
        else:
            if not character_id:
                raise HTTPException(status_code=400, detail="character or persona required")
            state = manager.set_active_character(character_id, mode=mode, reason=reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "state": state}


__all__ = ["router"]
