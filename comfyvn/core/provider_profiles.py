from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProviderProfile:
    """Curated metadata used to prefill remote provider templates and advisor hints."""

    id: str
    name: str
    kind: str
    service: str
    base_url: str
    default_gpu: str
    auth_fields: List[str]
    priority: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    policy_hints: Dict[str, str] = field(default_factory=dict)
    preferred_workloads: List[str] = field(default_factory=list)


CURATED_PROVIDER_PROFILES: List[ProviderProfile] = [
    ProviderProfile(
        id="local",
        name="Local ComfyUI",
        kind="local",
        service="comfyui",
        base_url="http://127.0.0.1:8188",
        default_gpu="auto",
        auth_fields=[],
        priority=0,
        metadata={
            "min_vram_gb": None,
            "cost": {"hourly_usd": 0.0, "billing_increment_minutes": 0},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": True,
            "cost_tier": 0,
        },
        policy_hints={
            "voice_synthesis": "Use local GPU when latency sensitive and VRAM requirements fit available hardware.",
            "cg_batch": "Validate local VRAM/utilization before committing long CG batches.",
            "translation": "Local CPU fallback acceptable for translation-only pipelines.",
        },
        preferred_workloads=["voice_synthesis", "translation"],
    ),
    ProviderProfile(
        id="local_llm",
        name="Local LLM Runtime",
        kind="local",
        service="llm_local",
        base_url="http://127.0.0.1:5005",
        default_gpu="cpu",
        auth_fields=[],
        priority=5,
        metadata={
            "min_vram_gb": None,
            "max_vram_gb": None,
            "cost": {"hourly_usd": 0.0, "billing_increment_minutes": 0},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": True,
            "model_formats": ["gguf", "ggml", "ollama"],
            "notes": "Offline llama.cpp/ollama-style runtime for persona dialogue authoring.",
            "cost_tier": 0,
        },
        policy_hints={
            "dialogue_authoring": "Use for privacy-sensitive scripting sessions and quick persona iterations.",
            "translation": "CPU-first pipeline; expect slower throughput on long documents.",
        },
        preferred_workloads=["dialogue_authoring", "translation"],
    ),
    ProviderProfile(
        id="runpod",
        name="RunPod",
        kind="remote",
        service="runpod",
        base_url="https://api.runpod.io/v2/",
        default_gpu="A10G",
        auth_fields=["api_key"],
        priority=10,
        metadata={
            "min_vram_gb": 12,
            "max_vram_gb": 24,
            "cost": {"hourly_usd": 0.46, "billing_increment_minutes": 1},
            "supports_large_assets": False,
            "supports_persistent_storage": False,
            "supports_long_running": True,
            "supports_short_burst": True,
            "regions": ["us-west", "eu-central"],
            "cost_tier": 2,
        },
        policy_hints={
            "voice_synthesis": "Burst voice or TTS imports spin up quickly; use serverless pods with auto-stop.",
            "cg_batch": "Select dedicated pods for long renders to avoid eviction from community nodes.",
            "translation": "Pair with CPU-friendly pod types; GPU optional unless TTS models requested.",
        },
        preferred_workloads=["voice_synthesis"],
    ),
    ProviderProfile(
        id="vast",
        name="Vast.ai",
        kind="remote",
        service="vast.ai",
        base_url="https://api.vast.ai/v0/",
        default_gpu="RTX4090",
        auth_fields=["api_key"],
        priority=20,
        metadata={
            "min_vram_gb": 16,
            "max_vram_gb": 48,
            "cost": {"hourly_usd": 0.39, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": False,
            "regions": ["marketplace"],
            "cost_tier": 1,
        },
        policy_hints={
            "voice_synthesis": "Queue delay possible; reserve on-demand nodes when latency matters.",
            "cg_batch": "Marketplace offers high VRAM GPUs ideal for CG super-res and animation bakes.",
            "translation": "CPU-only instances cheaper if GPU not required.",
        },
        preferred_workloads=["cg_batch"],
    ),
    ProviderProfile(
        id="lambda",
        name="Lambda Labs",
        kind="remote",
        service="lambda",
        base_url="https://cloud.lambdalabs.com/api/v1/",
        default_gpu="A100",
        auth_fields=["api_key"],
        priority=30,
        metadata={
            "min_vram_gb": 24,
            "max_vram_gb": 80,
            "cost": {"hourly_usd": 1.10, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": False,
            "regions": ["us-east", "us-west"],
            "cost_tier": 3,
        },
        policy_hints={
            "cg_batch": "High VRAM nodes handle multi-hour CG baking and diffusion upscales.",
            "voice_synthesis": "Overkill for short TTS workloads; consider RunPod or local first.",
            "translation": "GPU optional; use if translation requires transformer fine-tuning.",
        },
        preferred_workloads=["cg_batch"],
    ),
    ProviderProfile(
        id="aws",
        name="AWS EC2",
        kind="remote",
        service="aws",
        base_url="https://ec2.amazonaws.com",
        default_gpu="g5.xlarge",
        auth_fields=["access_key", "secret_key", "region"],
        priority=40,
        metadata={
            "min_vram_gb": 24,
            "max_vram_gb": 48,
            "cost": {"hourly_usd": 1.05, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": False,
            "regions": ["global"],
            "egress_notice": "Outbound data billed per GB; keep assets in-region.",
            "cost_tier": 3,
        },
        policy_hints={
            "cg_batch": "Use spot instances for render farms; ensure S3 bucket in same region to avoid egress.",
            "voice_synthesis": "Latency impacted by boot time; pre-warm AMIs if used interactively.",
            "translation": "CPU optimized instances cheaper unless GPU translation models required.",
        },
        preferred_workloads=["cg_batch"],
    ),
    ProviderProfile(
        id="azure",
        name="Azure NV",
        kind="remote",
        service="azure",
        base_url="https://management.azure.com",
        default_gpu="NC4as_T4_v3",
        auth_fields=["tenant_id", "client_id", "client_secret", "subscription_id"],
        priority=50,
        metadata={
            "min_vram_gb": 16,
            "max_vram_gb": 48,
            "cost": {"hourly_usd": 1.00, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": False,
            "regions": ["regional"],
            "egress_notice": "Cross-region transfers incur cost; keep datasets in matching storage account.",
            "cost_tier": 3,
        },
        policy_hints={
            "cg_batch": "Quota requests required for NV-series GPUs; schedule ahead for big CG imports.",
            "voice_synthesis": "Combine with Azure Cognitive Services for voice pipelines to keep data in-region.",
            "translation": "Stay within required residency zone (EU/US) per client contract.",
        },
        preferred_workloads=["translation", "cg_batch"],
    ),
    ProviderProfile(
        id="coreweave",
        name="CoreWeave",
        kind="remote",
        service="coreweave",
        base_url="https://api.coreweave.com",
        default_gpu="A40",
        auth_fields=["api_key", "organization_id"],
        priority=55,
        metadata={
            "min_vram_gb": 24,
            "max_vram_gb": 48,
            "cost": {"hourly_usd": 0.95, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": True,
            "regions": ["us-east", "us-west"],
            "cost_tier": 3,
        },
        policy_hints={
            "cg_batch": "Kubernetes native scheduling handles multi-job CG pipelines with persistent volumes.",
            "voice_synthesis": "Dedicated clusters offer predictable latency for realtime synthesis.",
            "translation": "GPU optional; leverage CPU pools for text-only translation.",
        },
        preferred_workloads=["cg_batch", "voice_synthesis"],
    ),
    ProviderProfile(
        id="google",
        name="Google Cloud",
        kind="remote",
        service="gcp",
        base_url="https://compute.googleapis.com",
        default_gpu="a2-highgpu-1g",
        auth_fields=["project_id", "service_account_json", "region"],
        priority=65,
        metadata={
            "min_vram_gb": 16,
            "max_vram_gb": 40,
            "cost": {"hourly_usd": 0.85, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": False,
            "regions": ["global"],
            "egress_notice": "Cross-region egress billed per GB; co-locate GCS buckets.",
            "cost_tier": 3,
        },
        policy_hints={
            "cg_batch": "A2 instances handle multi-hour GPU jobs; enable sustained-use discounts for savings.",
            "voice_synthesis": "Combine with Vertex AI batching when workloads exceed local capacity.",
            "translation": "Use same region as Translation API to avoid cross-region charges.",
        },
        preferred_workloads=["cg_batch", "translation"],
    ),
    ProviderProfile(
        id="paperspace",
        name="Paperspace",
        kind="remote",
        service="paperspace",
        base_url="https://api.paperspace.io",
        default_gpu="A4000",
        auth_fields=["api_key", "project"],
        priority=60,
        metadata={
            "min_vram_gb": 16,
            "max_vram_gb": 32,
            "cost": {"hourly_usd": 0.78, "billing_increment_minutes": 60},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": True,
            "regions": ["nyc3", "ams1"],
            "cost_tier": 2,
        },
        policy_hints={
            "cg_batch": "Persistent volumes handle multi-stage CG importer caching.",
            "voice_synthesis": "Use Gradient notebooks for interactive vocal edits with GPU acceleration.",
            "translation": "CPU nodes available when GPU not required.",
        },
        preferred_workloads=["cg_batch", "voice_synthesis"],
    ),
    ProviderProfile(
        id="unraid",
        name="unRAID / LAN Node",
        kind="remote",
        service="lan",
        base_url="http://unraid.local:8001",
        default_gpu="local",
        auth_fields=["endpoint", "api_token"],
        priority=70,
        metadata={
            "min_vram_gb": 8,
            "max_vram_gb": 24,
            "cost": {"hourly_usd": 0.0, "billing_increment_minutes": 0},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": True,
            "regions": ["on-prem"],
            "cost_tier": 0,
        },
        policy_hints={
            "cg_batch": "Great for overnight CG renders when idle LAN GPU available.",
            "voice_synthesis": "Low-latency if network close; ensure SSH tunnel secured.",
            "translation": "Keeps content on-prem for sensitive localization projects.",
        },
        preferred_workloads=["cg_batch", "voice_synthesis", "translation"],
    ),
    ProviderProfile(
        id="onprem_ssh",
        name="On-Prem SSH/NFS",
        kind="remote",
        service="ssh",
        base_url="ssh://gpu-host",
        default_gpu="custom",
        auth_fields=["hostname", "username", "ssh_key_path", "nfs_mount"],
        priority=80,
        metadata={
            "min_vram_gb": 8,
            "max_vram_gb": None,
            "cost": {"hourly_usd": 0.0, "billing_increment_minutes": 0},
            "supports_large_assets": True,
            "supports_persistent_storage": True,
            "supports_long_running": True,
            "supports_short_burst": True,
            "regions": ["on-prem"],
            "cost_tier": 0,
        },
        policy_hints={
            "cg_batch": "Mount shared NFS volumes for texture caches before submitting renders.",
            "voice_synthesis": "Ensure audio assets stored locally to meet residency requirements.",
            "translation": "Ideal when legal mandates forbid cloud processing.",
        },
        preferred_workloads=["translation", "cg_batch"],
    ),
]


PROFILE_MAP = {profile.id: profile for profile in CURATED_PROVIDER_PROFILES}


def get_profile_by_service(service: str) -> ProviderProfile | None:
    service = (service or "").lower()
    for profile in CURATED_PROVIDER_PROFILES:
        if profile.service == service:
            return profile
    return None


__all__ = [
    "ProviderProfile",
    "CURATED_PROVIDER_PROFILES",
    "PROFILE_MAP",
    "get_profile_by_service",
]
