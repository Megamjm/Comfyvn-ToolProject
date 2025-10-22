"""
Model registry utilities for ComfyVN.

Provides helpers to load the neutral LLM registry and resolve adapter
configurations.  The registry itself is JSON so it can be safely edited by
tooling without code changes.
"""

from __future__ import annotations

from .registry import (
    AdapterConfig,
    ModelEntry,
    ProviderConfig,
    get_registry,
    iter_models,
    iter_providers,
    refresh_registry,
    resolve_provider,
)
from .runtime_registry import (
    RuntimeAdapter,
    RuntimeRegistry,
    register_runtime_adapter,
    runtime_registry,
)

__all__ = [
    "AdapterConfig",
    "ProviderConfig",
    "ModelEntry",
    "get_registry",
    "iter_models",
    "iter_providers",
    "refresh_registry",
    "resolve_provider",
    "RuntimeAdapter",
    "RuntimeRegistry",
    "register_runtime_adapter",
    "runtime_registry",
]
