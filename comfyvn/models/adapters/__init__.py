"""
Adapter registry for ComfyVN LLM providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Mapping, Type

from .anthropic_compat import AnthropicCompatAdapter
from .base import Adapter, AdapterError, ChatResult
from .lmstudio import LMStudioAdapter
from .ollama import OllamaAdapter
from .openai_compat import OpenAICompatAdapter
from .proxy import ProxyAdapter
from .stub import StubAdapter

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from comfyvn.models.registry import AdapterConfig

ADAPTERS: Dict[str, Type[Adapter]] = {
    OpenAICompatAdapter.name: OpenAICompatAdapter,
    LMStudioAdapter.name: LMStudioAdapter,
    OllamaAdapter.name: OllamaAdapter,
    AnthropicCompatAdapter.name: AnthropicCompatAdapter,
    ProxyAdapter.name: ProxyAdapter,
    StubAdapter.name: StubAdapter,
}


def get_adapter_class(name: str) -> Type[Adapter] | None:
    key = name.strip().lower()
    for adapter_name, adapter_cls in ADAPTERS.items():
        if adapter_name.lower() == key:
            return adapter_cls
    return None


def create_adapter(
    adapter_name: str,
    *,
    base_url: str,
    api_key: str | None = None,
    timeout: float | None = None,
    headers: Mapping[str, Any] | None = None,
    settings: Mapping[str, Any] | None = None,
) -> Adapter:
    adapter_cls = get_adapter_class(adapter_name)
    if not adapter_cls:
        raise AdapterError(f"No adapter registered for '{adapter_name}'")
    return adapter_cls(
        base_url,
        api_key=api_key,
        timeout=timeout,
        headers=headers,
        settings=settings,
    )


def adapter_from_config(config: "AdapterConfig") -> Adapter:
    return create_adapter(
        config.adapter,
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=config.timeout,
        headers=config.headers,
        settings=config.settings,
    )


__all__ = [
    "Adapter",
    "AdapterError",
    "ChatResult",
    "OpenAICompatAdapter",
    "LMStudioAdapter",
    "OllamaAdapter",
    "AnthropicCompatAdapter",
    "ProxyAdapter",
    "StubAdapter",
    "adapter_from_config",
    "create_adapter",
    "get_adapter_class",
]
