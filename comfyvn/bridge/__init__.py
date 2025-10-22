"""Bridge adapters connecting ComfyVN subsystems to external services."""

from .comfy import (
    ArtifactDescriptor,
    ComfyBridgeError,
    ComfyUIBridge,
    RenderContext,
    RenderJob,
    RenderResult,
)
from .comfy_hardening import (
    CharacterLoRARegistry,
    HardenedBridgeError,
    HardenedBridgeUnavailable,
    HardenedComfyBridge,
    LoRAEntry,
)
from .comfy_stream import PreviewCollector
from .music_adapter import remix
from .remote import RemoteBridge, RemoteCapabilityReport
from .tts import TTSBridge, TTSBridgeConfig, TTSBridgeResult
from .tts_adapter import synthesize

__all__ = [
    "ArtifactDescriptor",
    "ComfyBridgeError",
    "ComfyUIBridge",
    "RenderContext",
    "RenderJob",
    "RenderResult",
    "HardenedComfyBridge",
    "HardenedBridgeError",
    "HardenedBridgeUnavailable",
    "CharacterLoRARegistry",
    "LoRAEntry",
    "PreviewCollector",
    "RemoteBridge",
    "RemoteCapabilityReport",
    "remix",
    "synthesize",
    "TTSBridge",
    "TTSBridgeConfig",
    "TTSBridgeResult",
]
