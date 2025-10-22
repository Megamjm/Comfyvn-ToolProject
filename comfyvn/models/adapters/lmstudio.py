"""
Adapter for LM Studio's OpenAI-compatible API.
"""

from __future__ import annotations

from typing import Any, Mapping

from .openai_compat import OpenAICompatAdapter


class LMStudioAdapter(OpenAICompatAdapter):
    name = "lmstudio"

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        headers: Mapping[str, Any] | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        merged_settings: dict[str, Any] = {"chat_path": "/chat/completions"}
        if settings:
            merged_settings.update(settings)
        super().__init__(
            base_url,
            api_key=api_key,
            timeout=timeout,
            headers=headers,
            settings=merged_settings,
        )


__all__ = ["LMStudioAdapter"]
