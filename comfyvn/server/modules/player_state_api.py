from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request

router = APIRouter(prefix="/player", tags=["Player Persona"])


def _persona_manager(request: Request):
    manager = getattr(request.app.state, "persona", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="persona manager unavailable")
    return manager


def _character_manager(request: Request):
    manager = getattr(request.app.state, "characters", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="character manager unavailable")
    return manager


@router.get("/state")
def state(request: Request) -> Dict[str, Any]:
    manager = _persona_manager(request)
    return {"ok": True, "data": manager.get_active_selection()}


@router.get("/personas")
def personas(
    request: Request, role: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    manager = _persona_manager(request)
    return {"ok": True, "data": {"items": manager.list_personas(role=role)}}


@router.get("/roster")
def roster(request: Request) -> Dict[str, Any]:
    persona_manager = _persona_manager(request)
    character_manager = _character_manager(request)
    return {
        "ok": True,
        "data": {
            "characters": character_manager.list_characters(),
            "personas": persona_manager.list_personas(),
            "active": persona_manager.get_active_selection(),
        },
    }


@router.post("/select")
def select(request: Request, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    manager = _persona_manager(request)
    persona_id = body.get("persona") or body.get("persona_id")
    character_id = body.get("character") or body.get("character_id")
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
        elif character_id:
            state = manager.set_active_character(character_id, mode=mode, reason=reason)
        else:
            raise HTTPException(status_code=400, detail="persona or character required")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "data": state}


@router.post("/import")
def import_character(
    request: Request, body: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    manager = _persona_manager(request)
    overwrite = bool(body.get("overwrite", False))
    auto_select = bool(body.get("auto_select", False))
    role = body.get("role", "player")

    source: Any
    if "character" in body:
        source = body["character"]
    elif "payload" in body:
        source = body["payload"]
    elif "path" in body:
        source = body["path"]
    else:
        # Treat remaining fields as character payload, excluding control keys.
        source = {
            k: v
            for k, v in body.items()
            if k not in {"role", "overwrite", "auto_select"}
        }

    try:
        result = manager.import_character(
            source,
            role=role,
            overwrite=overwrite,
            auto_select=auto_select,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    roster = {
        "characters": _character_manager(request).list_characters(),
        "personas": manager.list_personas(),
        "active": manager.get_active_selection(),
    }
    return {"ok": True, "data": {**result, "roster": roster}}


@router.post("/refresh")
def refresh(request: Request) -> Dict[str, Any]:
    manager = _persona_manager(request)
    manager.reload()
    return {
        "ok": True,
        "data": {
            "state": manager.get_active_selection(),
            "personas": manager.list_personas(),
            "characters": _character_manager(request).list_characters(),
        },
    }


@router.post("/process")
def process_persona(
    request: Request, body: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    manager = _persona_manager(request)
    persona_id = body.get("persona") or body.get("persona_id")
    scene_id = body.get("scene") or body.get("scene_id")
    detail_level = body.get("detail") or body.get("detail_level")
    export = bool(body.get("export", False))
    try:
        result = manager.process_persona(
            persona_id,
            scene_id=scene_id,
            detail_level=detail_level,
            export=export,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "data": result}


__all__ = ["router"]
