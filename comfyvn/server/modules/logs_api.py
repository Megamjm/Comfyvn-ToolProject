from PySide6.QtGui import QAction
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from comfyvn.config.runtime_paths import logs_dir, jobs_log_file
router = APIRouter()

@router.get("/jobs_state")
async def jobs_state():
    p = logs_dir("jobs_state.json")
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="application/json", filename="jobs_state.json")

@router.get("/job/{job_id}")
async def job_log(job_id: str):
    p = jobs_log_file(job_id)
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="application/json", filename=f"job_{job_id}.jsonl")
