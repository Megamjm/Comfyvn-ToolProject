from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from comfyvn.bridge.comfy import ComfyBridgeError
from comfyvn.core.comfyui_audio import (
    ComfyUIAudioRunner,
    ComfyUIWorkflowConfig,
    ComfyUIWorkflowError,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TTSBridgeConfig:
    """Configuration for the TTS bridge."""

    base_url: str = "http://127.0.0.1:8188"
    workflow_path: Path = Path("comfyvn/workflows/voice_clip_xtts.json")
    output_dir: Path = Path("exports/audio/tts")
    poll_interval: float = 1.5
    timeout: float = 180.0
    ensure_identity: bool = True
    preferred_engines: Sequence[str] = ("xtts", "indextts2", "vibevoice")

    def to_comfy_config(self) -> ComfyUIWorkflowConfig:
        return ComfyUIWorkflowConfig(
            base_url=self.base_url,
            workflow_path=self.workflow_path,
            output_dir=self.output_dir,
            poll_interval=self.poll_interval,
            timeout=self.timeout,
        )


@dataclass(slots=True)
class TTSBridgeResult:
    """Result of a TTS bridge invocation."""

    files: List[Path]
    prompt_id: str
    workflow: str
    base_url: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class TTSBridge:
    """High-level helper for executing voice workflows through ComfyUI."""

    def __init__(self, config: TTSBridgeConfig) -> None:
        self.config = config
        self.runner = ComfyUIAudioRunner(config.to_comfy_config())

    def synthesize_clip(
        self,
        clip: Dict[str, Any],
        *,
        character: Optional[Dict[str, Any]] = None,
        scene: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
        output_types: Iterable[str] = ("audio",),
    ) -> TTSBridgeResult:
        """Render a single voice clip using the configured ComfyUI workflow."""
        ready, reason = self.runner.is_ready()
        if not ready:
            raise ComfyBridgeError(reason or "ComfyUI voice workflow unavailable")

        context = self._build_context(clip, character=character, scene=scene, extra=extra_context)
        LOGGER.debug(
            "Submitting TTS clip %s (%s) to ComfyUI via %s",
            clip.get("id"),
            clip.get("engine"),
            self.config.workflow_path,
        )

        try:
            files, payload = self.runner.run(context=context, output_types=output_types)
        except ComfyUIWorkflowError as exc:
            raise ComfyBridgeError(str(exc)) from exc

        metadata = {
            "clip": clip,
            "character": character or {},
            "scene": scene or {},
            "workflow": payload.get("workflow"),
            "prompt_id": payload.get("prompt_id"),
            "base_url": payload.get("base_url"),
        }
        metadata.update(extra_context or {})

        return TTSBridgeResult(
            files=files,
            prompt_id=str(payload.get("prompt_id")),
            workflow=str(payload.get("workflow")),
            base_url=str(payload.get("base_url")),
            metadata=metadata,
        )

    def _build_context(
        self,
        clip: Dict[str, Any],
        *,
        character: Optional[Dict[str, Any]],
        scene: Optional[Dict[str, Any]],
        extra: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        character = character or {}
        scene = scene or {}
        context: Dict[str, Any] = {
            "clip_id": clip.get("id"),
            "text": clip.get("text"),
            "lang": clip.get("lang") or character.get("voice", {}).get("lang") or "en",
            "engine": clip.get("engine") or self._select_engine(clip),
            "speaker": clip.get("speaker") or character.get("display_name") or character.get("name"),
            "character_id": character.get("id"),
            "scene_id": scene.get("id"),
            "rvc_model": clip.get("post", {}).get("rvc_model") or character.get("voice", {}).get("rvc_model"),
            "rvc_mix": clip.get("post", {}).get("mix"),
            "target_ms": clip.get("timing", {}).get("target_ms"),
            "voice_refs": clip.get("ref_audio") or character.get("voice", {}).get("voice_refs") or [],
            "style_tags": character.get("style", {}).get("tags") or [],
            "seed": clip.get("seed"),
        }
        if extra:
            context.update(extra)
        # Render metrics for provenance
        context["metadata_json"] = json.dumps(
            {
                "clip": clip,
                "character": character,
                "scene": scene,
            },
            ensure_ascii=False,
        )
        return context

    def _select_engine(self, clip: Dict[str, Any]) -> str:
        preferred = clip.get("engine")
        if preferred:
            return preferred
        prefer = clip.get("preferred_tts") or clip.get("voice", {}).get("preferred_tts")
        if isinstance(prefer, str):
            for token in prefer.split("|"):
                token = token.strip()
                if token:
                    return token
        for engine in self.config.preferred_engines:
            return engine
        return "xtts"


__all__ = ["TTSBridge", "TTSBridgeConfig", "TTSBridgeResult"]

