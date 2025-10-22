"""
Adapter base classes for LLM providers.

Each adapter implements a ``chat`` method that accepts the OpenAI-style list of
messages and returns a :class:`ChatResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, MutableMapping

import requests

DEFAULT_TIMEOUT = 30.0


class AdapterError(RuntimeError):
    """Raised when an adapter fails to produce a response."""


@dataclass(slots=True)
class ChatResult:
    """Normalized chat response returned by adapters."""

    reply: str
    raw: Dict[str, Any] = field(default_factory=dict)
    status: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)


def _clone_headers(headers: Mapping[str, Any] | None) -> Dict[str, str]:
    if not headers:
        return {}
    return {
        str(key): str(value)
        for key, value in headers.items()
        if key and value is not None
    }


class Adapter:
    """Base adapter interface."""

    name = "base"

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        headers: Mapping[str, Any] | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.timeout = float(timeout) if timeout else DEFAULT_TIMEOUT
        self.headers = _clone_headers(headers)
        self.settings = dict(settings or {})

    def _resolve_url(self, path: str | None) -> str:
        if not self.base_url:
            raise AdapterError(f"{self.name} adapter is missing a base URL")
        if not path:
            return self.base_url
        path = str(path).strip()
        if not path:
            return self.base_url
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _base_headers(self) -> Dict[str, str]:
        headers = dict(self.headers)
        if self.api_key:
            headers.setdefault("Authorization", f"Bearer {self.api_key}")
        return headers

    def _post_json(
        self,
        path: str,
        payload: MutableMapping[str, Any],
        *,
        headers: Mapping[str, Any] | None = None,
    ) -> tuple[requests.Response, dict[str, Any]]:
        url = self._resolve_url(path)
        merged_headers = self._base_headers()
        if headers:
            merged_headers.update(_clone_headers(headers))
        try:
            response = requests.post(
                url,
                json=payload,
                headers=merged_headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:  # pragma: no cover - network I/O
            raise AdapterError(f"{self.name} adapter request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}
        if response.status_code >= 400:
            message = data.get("error") if isinstance(data, Mapping) else data
            raise AdapterError(
                f"{self.name} adapter returned {response.status_code}: {message}"
            )
        if not isinstance(data, dict):
            data = {"data": data}
        return response, data

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        **kwargs: Any,
    ) -> ChatResult:
        """Submit a chat request. Must be implemented by subclasses."""
        raise NotImplementedError


__all__ = ["Adapter", "AdapterError", "ChatResult", "DEFAULT_TIMEOUT"]
