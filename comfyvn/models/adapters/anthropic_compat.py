"""
Adapter for Anthropic-compatible endpoints.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

from .base import Adapter, AdapterError, ChatResult

DEFAULT_MAX_TOKENS = 1024
DEFAULT_VERSION = "2023-06-01"


def _coerce_messages(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    coerced: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            role = "user"
        content = item.get("content")
        if isinstance(content, list):
            blocks = []
            for block in content:
                if isinstance(block, Mapping):
                    blocks.append(dict(block))
                else:
                    blocks.append({"type": "text", "text": str(block)})
            coerced.append({"role": role, "content": blocks})
            continue
        if content is None:
            coerced.append({"role": role, "content": ""})
        else:
            coerced.append({"role": role, "content": str(content)})
    return coerced


class AnthropicCompatAdapter(Adapter):
    """Adapter for the Anthropic Messages API."""

    name = "anthropic_compat"

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        **kwargs: Any,
    ) -> ChatResult:
        if not self.api_key:
            raise AdapterError("anthropic_compat adapter requires an API key")
        max_tokens = kwargs.pop(
            "max_tokens", self.settings.get("max_tokens", DEFAULT_MAX_TOKENS)
        )
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            max_tokens = DEFAULT_MAX_TOKENS
        system_prompt = kwargs.pop("system", None)
        payload: MutableMapping[str, Any] = {
            "model": model,
            "max_tokens": max(1, max_tokens),
            "messages": _coerce_messages(messages),
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload.update(
            {key: value for key, value in kwargs.items() if value is not None}
        )
        version = self.settings.get("anthropic_version", DEFAULT_VERSION)
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": version,
        }
        response, data = self._post_json("/messages", payload, headers=headers)
        content = data.get("content")
        reply = ""
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, Mapping):
                text = first.get("text")
                if isinstance(text, str):
                    reply = text
        if not reply:
            reply = str(data.get("output_text") or data.get("text") or "")
        usage = data.get("usage") if isinstance(data, Mapping) else {}
        return ChatResult(
            reply=reply,
            raw=data,
            status=response.status_code,
            headers=dict(response.headers),
            usage=usage if isinstance(usage, Mapping) else {},
        )


__all__ = ["AnthropicCompatAdapter"]
