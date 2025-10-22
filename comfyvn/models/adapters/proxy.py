from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

from .base import Adapter, AdapterError, ChatResult


class ProxyAdapter(Adapter):
    """Generic HTTP proxy adapter that forwards chat requests to `/chat`."""

    name = "proxy"

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        **kwargs: Any,
    ) -> ChatResult:
        payload: MutableMapping[str, Any] = {
            "model": model,
            "messages": [dict(message) for message in messages],
        }
        if kwargs:
            payload["params"] = dict(kwargs)
        response, data = self._post_json("/chat", payload)
        reply = ""
        if isinstance(data, Mapping):
            reply = str(
                data.get("reply") or data.get("content") or data.get("text") or ""
            ).strip()
        if not reply:
            raise AdapterError("proxy adapter returned an empty reply")
        return ChatResult(
            reply=reply,
            raw=dict(data),
            status=response.status_code,
            headers=dict(response.headers),
        )


__all__ = ["ProxyAdapter"]
