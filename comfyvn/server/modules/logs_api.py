from PySide6.QtGui import QAction
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
router = APIRouter()

@router.get("/jobs_state")
async def jobs_state():
    p = Path("./logs/jobs_state.json")
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="application/json", filename="jobs_state.json")

@router.get("/job/{job_id}")
async def job_log(job_id: str):
    p = Path("./logs/job_logs") / f"{job_id}.jsonl"
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="application/json", filename=f"job_{job_id}.jsonl")