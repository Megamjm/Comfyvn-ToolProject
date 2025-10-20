from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

LOGGER = logging.getLogger("comfyvn.audio.music")


def remix_track(
    *,
    scene_id: str,
    target_style: str,
    source_track: Optional[str] = None,
    seed: Optional[int] = None,
    mood_tags: Optional[list[str]] = None,
) -> Tuple[str, str]:
    """Stub remix engine producing metadata-rich artifacts."""

    target = target_style.strip() or "default"
    scene = scene_id.strip() or "scene-unknown"
    digest_src = "|".join(
        [
            scene,
            target,
            source_track or "",
            ",".join(sorted(mood_tags or [])),
            str(seed or 0),
        ]
    )
    digest = hashlib.sha1(digest_src.encode("utf-8")).hexdigest()[:12]

    outdir = Path("exports/music")
    outdir.mkdir(parents=True, exist_ok=True)

    artifact = outdir / f"{scene}_{target}_{digest}.txt"
    artifact.write_text(
        "\n".join(
            [
                f"SCENE={scene}",
                f"TARGET_STYLE={target}",
                f"SOURCE={source_track or 'auto'}",
                f"MOOD={','.join(mood_tags or [])}",
                f"SEED={seed or 0}",
                "NOTE=Stub remix artifact (replace with rendered audio)",
            ]
        ),
        encoding="utf-8",
    )

    payload = {
        "scene_id": scene,
        "target_style": target,
        "source_track": source_track,
        "mood_tags": mood_tags or [],
        "seed": seed,
        "created_at": time.time(),
    }
    sidecar = artifact.with_suffix(".json")
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    LOGGER.info(
        "Music remix scene=%s target=%s artifact=%s",
        scene,
        target,
        artifact.name,
    )
    return str(artifact), str(sidecar)
