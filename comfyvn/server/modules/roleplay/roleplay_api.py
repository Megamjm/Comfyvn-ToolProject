# comfyvn/server/modules/roleplay/roleplay_api.py
# 🤝 Roleplay API — independent importer & converter
# [ComfyVN_Architect | Roleplay Import & Collaboration Chat]

import os, json, traceback
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from .parser import RoleplayParser
from .formatter import RoleplayFormatter

# -------------------------------------------------------------------
# Router setup
# -------------------------------------------------------------------
router = APIRouter(prefix="/roleplay", tags=["Roleplay Import"])

# -------------------------------------------------------------------
# Directories
# -------------------------------------------------------------------
RAW_DIR = "./data/roleplay/raw"
CONVERTED_DIR = "./data/roleplay/converted"
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(CONVERTED_DIR, exist_ok=True)


# -------------------------------------------------------------------
# 📥 Import Route
# -------------------------------------------------------------------
@router.post("/import")
async def import_roleplay(
    file: UploadFile = File(...),
    world_tag: str = Form("unlinked"),
    source: str = Form("manual"),
):
    """
    Upload any plain text or chat log file (from SillyTavern, Discord, etc.)
    and convert it into a ComfyVN-compatible scene JSON.
    """
    try:
        raw_text = (await file.read()).decode("utf-8", errors="ignore")

        # Save raw upload for archival
        raw_path = os.path.join(RAW_DIR, file.filename)
        with open(raw_path, "w", encoding="utf-8") as raw_f:
            raw_f.write(raw_text)

        parser = RoleplayParser()
        formatter = RoleplayFormatter()

        parsed = parser.parse_text(raw_text)
        participants = list({line["speaker"] for line in parsed})
        scene = formatter.format_scene(parsed, participants, world_tag, source)

        output_path = os.path.join(CONVERTED_DIR, f"{scene['scene_id']}.json")
        formatter.save_scene(scene, output_path)

        return JSONResponse(
            {
                "status": "ok",
                "scene_id": scene["scene_id"],
                "participants": participants,
                "lines": len(scene.get("lines", [])),
                "world_tag": world_tag,
                "source": source,
                "output": output_path,
            }
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


# -------------------------------------------------------------------
# 👁️ Preview Scene Route
# -------------------------------------------------------------------
@router.get("/preview/{scene_id}")
async def preview_scene(scene_id: str):
    """
    Fetch and preview a converted roleplay scene JSON by ID.
    """
    path = os.path.join(CONVERTED_DIR, f"{scene_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Scene not found")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load scene: {e}")


# -------------------------------------------------------------------
# 🗂️ List Available Scenes
# -------------------------------------------------------------------
@router.get("/list")
async def list_scenes():
    """
    List all imported and converted roleplay scenes.
    """
    scenes = []
    for f in os.listdir(CONVERTED_DIR):
        if f.endswith(".json"):
            scenes.append(f.replace(".json", ""))
    return {"count": len(scenes), "scenes": scenes}


# -------------------------------------------------------------------
# 🧠 Scene Categorization Endpoint
# -------------------------------------------------------------------
@router.get("/categories")
async def list_roleplay_categories():
    """
    Returns categorized lists of roleplay files:
    - raw: unprocessed uploads
    - converted: parsed/converted to VN JSON
    - ready: playable scenes already in data/scenes
    """
    categories = {"raw": [], "converted": [], "ready": []}

    # Raw uploads
    if os.path.exists(RAW_DIR):
        for f in os.listdir(RAW_DIR):
            if f.endswith(".txt") or f.endswith(".json"):
                categories["raw"].append(f)

    # Converted scenes
    if os.path.exists(CONVERTED_DIR):
        for f in os.listdir(CONVERTED_DIR):
            if f.endswith(".json"):
                categories["converted"].append(f.replace(".json", ""))

    # Ready (finalized) scenes
    ready_dir = "./data/scenes"
    if os.path.exists(ready_dir):
        for f in os.listdir(ready_dir):
            if f.endswith(".json"):
                categories["ready"].append(f.replace(".json", ""))

    return categories


# -------------------------------------------------------------------
# 🔄 Promotion & Reversion System
# -------------------------------------------------------------------


@router.post("/promote/{scene_id}")
async def promote_scene(scene_id: str):
    """
    Promote a converted scene to 'ready' status by moving it
    from /data/roleplay/converted → /data/scenes.
    """
    src = os.path.join(CONVERTED_DIR, f"{scene_id}.json")
    dst_dir = "./data/scenes"
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{scene_id}.json")

    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="Converted scene not found.")
    try:
        os.replace(src, dst)
        return {
            "status": "ok",
            "message": f"Scene '{scene_id}' promoted to ready.",
            "target": dst,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Promotion failed: {e}")


@router.post("/revert/{scene_id}")
async def revert_scene(scene_id: str):
    """
    Revert a 'ready' scene back to converted by moving it
    from /data/scenes → /data/roleplay/converted.
    """
    src = os.path.join("./data/scenes", f"{scene_id}.json")
    dst_dir = CONVERTED_DIR
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{scene_id}.json")

    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="Ready scene not found.")
    try:
        os.replace(src, dst)
        return {
            "status": "ok",
            "message": f"Scene '{scene_id}' reverted to converted.",
            "target": dst,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reversion failed: {e}")


@router.post("/convert_raw/{filename}")
async def convert_raw(filename: str):
    """
    Convert a raw uploaded file (in /data/roleplay/raw)
    into a formatted converted scene (in /converted).
    """
    raw_path = os.path.join(RAW_DIR, filename)
    if not os.path.exists(raw_path):
        raise HTTPException(status_code=404, detail="Raw file not found.")

    parser = RoleplayParser()
    formatter = RoleplayFormatter()

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        parsed = parser.parse_text(raw_text)
        participants = list({l["speaker"] for l in parsed})
        scene = formatter.format_scene(parsed, participants, "unlinked", "auto-convert")

        output = os.path.join(CONVERTED_DIR, f"{scene['scene_id']}.json")
        formatter.save_scene(scene, output)
        return {
            "status": "ok",
            "scene_id": scene["scene_id"],
            "lines": len(scene["lines"]),
            "output": output,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
