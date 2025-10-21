from __future__ import annotations

"""
Music remix adapter stub.

Provides a queued job placeholder that records the requested track/style pair
and writes a planning document for downstream orchestration layers.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict

LOGGER = logging.getLogger(__name__)

_REMIX_ROOT = Path("data/audio/remix")


def remix(track_path: str, style: str) -> Dict[str, str]:
    """
    Stub out a remix request by generating a job id and persisting a plan.

    Returns metadata that can be forwarded to UI clients until real DSP
    integration lands.
    """
    job_id = str(uuid.uuid4())
    job_root = _REMIX_ROOT / job_id
    job_root.mkdir(parents=True, exist_ok=True)

    plan = {
        "track": track_path,
        "style": style,
        "status": "queued",
    }
    (job_root / "plan.json").write_text(json.dumps(plan, indent=2))

    LOGGER.info(
        "Queued music remix job %s track=%s style=%s",
        job_id,
        track_path or "<none>",
        style or "<none>",
    )

    return {"job": job_id, "artifact": str(job_root)}
