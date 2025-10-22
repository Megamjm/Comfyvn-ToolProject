from __future__ import annotations

from typing import Any, Iterable, Mapping

from .base import Adapter, ChatResult


class StubAdapter(Adapter):
    """
    Offline adapter that echoes the last user message.

    Used for GUI tests and modder tooling when no networked LLM is available.
    """

    name = "stub"

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        **_: Any,
    ) -> ChatResult:
        last_user = ""
        history = []
        for message in messages:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "").strip()
            history.append({"role": role, "content": content})
            if role == "user":
                last_user = content
        reply = last_user or f"(stub:{model}) Ready when you are."
        return ChatResult(
            reply=reply,
            raw={"messages": history},
            status=200,
            headers={},
            usage={"total_tokens": len(reply.split())},
        )


__all__ = ["StubAdapter"]
