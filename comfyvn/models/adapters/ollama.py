"""
Adapter for the Ollama REST API.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

from .base import Adapter, ChatResult


def _coerce_messages(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    coerced: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, Mapping):
            continue
        role = str(msg.get("role") or "").strip() or "user"
        content = msg.get("content")
        if isinstance(content, list):
            text = "\n".join(str(part) for part in content)
        else:
            text = str(content or "")
        coerced.append({"role": role, "content": text})
    return coerced


class OllamaAdapter(Adapter):
    """Adapter for Ollama's `/api/chat` entrypoint."""

    name = "ollama"

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        **kwargs: Any,
    ) -> ChatResult:
        options = kwargs.pop("options", None)
        payload: MutableMapping[str, Any] = {
            "model": model,
            "messages": _coerce_messages(messages),
            "stream": bool(kwargs.pop("stream", False)),
        }
        if options:
            payload["options"] = options
        payload.update(
            {key: value for key, value in kwargs.items() if value is not None}
        )
        path = self.settings.get("chat_path") or "/api/chat"
        response, data = self._post_json(path, payload)
        message = data.get("message")
        reply = ""
        if isinstance(message, Mapping):
            reply = str(message.get("content") or "")
        if not reply:
            reply = str(data.get("response") or data.get("text") or "")
        usage = data.get("usage") if isinstance(data, Mapping) else {}
        return ChatResult(
            reply=reply,
            raw=data,
            status=response.status_code,
            headers=dict(response.headers),
            usage=usage if isinstance(usage, Mapping) else {},
        )


__all__ = ["OllamaAdapter"]
