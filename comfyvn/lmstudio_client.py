"""
LM Studio helper utilities for ComfyVN.

Provides simple health checks and a sample chat call against the
OpenAI-compatible LM Studio HTTP API.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, Optional

import requests

DEFAULT_BASE = "http://localhost:1234/v1"


def _load_config(path: str = "comfyvn.json") -> Dict[str, Any]:
    cfg_path = pathlib.Path(path)
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_base_url() -> str:
    cfg = _load_config()
    return (
        os.getenv("LMSTUDIO_URL")
        or cfg.get("lmstudio", {}).get("base_url")
        or cfg.get("integrations", {}).get("lmstudio_base_url")
        or DEFAULT_BASE
    )


def healthcheck(timeout: float = 2.5) -> Dict[str, Any]:
    base = get_base_url().rstrip("/")
    url = f"{base}/models"
    try:
        response = requests.get(url, timeout=timeout)
        ok = response.status_code == 200
        data = response.json() if ok else {}
        models = data.get("data", []) if isinstance(data, dict) else []
        return {"ok": ok, "base": base, "status": response.status_code, "models": models}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"ok": False, "base": base, "error": str(exc)}


def sample_chat(
    prompt: str = "Say 'pong'.",
    model: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    base = get_base_url().rstrip("/")
    payload = {
        "model": model or "auto",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "stream": False,
    }
    try:
        response = requests.post(f"{base}/chat/completions", json=payload, timeout=timeout)
        data = response.json()
        text = ""
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                text = message.get("content", "")
        return {"ok": response.status_code == 200, "status": response.status_code, "text": text, "raw": data}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"ok": False, "base": base, "error": str(exc)}


if __name__ == "__main__":
    print("[L1] checking LM Studio…")
    print(healthcheck())
