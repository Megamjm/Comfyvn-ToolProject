"""Bridge adapters connecting ComfyVN subsystems to external services."""

from .comfy import (ArtifactDescriptor, ComfyBridgeError, ComfyUIBridge,
                    RenderContext, RenderJob, RenderResult)
from .remote import RemoteBridge, RemoteCapabilityReport
from .tts import TTSBridge, TTSBridgeConfig, TTSBridgeResult

__all__ = [
    "ArtifactDescriptor",
    "ComfyBridgeError",
    "ComfyUIBridge",
    "RenderContext",
    "RenderJob",
    "RenderResult",
    "RemoteBridge",
    "RemoteCapabilityReport",
    "TTSBridge",
    "TTSBridgeConfig",
    "TTSBridgeResult",
]
