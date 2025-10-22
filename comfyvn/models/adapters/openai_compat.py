"""
Adapter for OpenAI-compatible chat endpoints.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

from .base import Adapter, AdapterError, ChatResult


def _coerce_messages(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    coerced: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        role = str(message.get("role") or "").strip() or "user"
        content = message.get("content")
        if isinstance(content, (list, tuple)):
            coerced.append({"role": role, "content": list(content)})
        elif content is None:
            coerced.append({"role": role, "content": ""})
        else:
            coerced.append({"role": role, "content": str(content)})
    return coerced


class OpenAICompatAdapter(Adapter):
    """Adapter for the OpenAI `/v1/chat/completions` schema."""

    name = "openai_compat"

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        **kwargs: Any,
    ) -> ChatResult:
        payload: MutableMapping[str, Any] = {
            "model": model,
            "messages": _coerce_messages(messages),
            "stream": bool(kwargs.pop("stream", False)),
        }
        payload.update(
            {key: value for key, value in kwargs.items() if value is not None}
        )
        path = self.settings.get("chat_path") or "/chat/completions"
        response, data = self._post_json(path, payload)
        reply = ""
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0] or {}
            if isinstance(message, Mapping):
                alt_message = message.get("message") or message
                if isinstance(alt_message, Mapping):
                    reply_value = alt_message.get("content")
                    if isinstance(reply_value, str):
                        reply = reply_value
        if not reply:
            reply = str(data.get("reply") or data.get("text") or "")
        usage = data.get("usage") if isinstance(data, Mapping) else {}
        return ChatResult(
            reply=reply,
            raw=data,
            status=response.status_code,
            headers=dict(response.headers),
            usage=usage if isinstance(usage, Mapping) else {},
        )


__all__ = ["OpenAICompatAdapter"]
