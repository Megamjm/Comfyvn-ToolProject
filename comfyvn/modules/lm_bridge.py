# comfyvn/modules/lm_bridge.py
# 🧠 Language Model Bridge – LM Studio / SillyTavern / OpenAI-Compatible
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import os, json, asyncio, httpx
from typing import Any, Dict, List, Optional

class LMBridge:
    """
    Provides async access to local or remote LLM endpoints.
    Supports:
      • LM Studio (OpenAI-compatible / localhost:1234)
      • SillyTavern (API relay mode)
      • Future cloud LLMs (OpenAI, Anthropic, etc.)
    """

    def __init__(
        self,
        lmstudio_base: str = "http://127.0.0.1:1234/v1",
        sillytavern_base: Optional[str] = None
    ) -> None:
        self.lmstudio_base = lmstudio_base
        self.sillytavern_base = sillytavern_base
        self.client: Optional[httpx.AsyncClient] = None

    # -------------------------------------------------
    # Lifecycle / Setup
    # -------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
        if not self.client:
            self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0))
        return self.client

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    # -------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------
    async def complete(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 200,
        system_prompt: Optional[str] = None,
        use_sillytavern: bool = False
    ) -> Dict[str, Any]:
        """
        Send a text generation request to the selected backend.
        Automatically falls back from SillyTavern → LM Studio → error.
        """
        client = await self._get_client()
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt or "You are ComfyVN Assistant."},
                         {"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # --- Try SillyTavern first if available ---
        if use_sillytavern and self.sillytavern_base:
            try:
                r = await client.post(f"{self.sillytavern_base}/v1/chat/completions", json=payload)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                print(f"[LMBridge] SillyTavern unreachable → {e}")

        # --- Fallback → LM Studio ---
        try:
            r = await client.post(f"{self.lmstudio_base}/chat/completions", json=payload)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -------------------------------------------------
    # Embeddings / Vector API (optional)
    # -------------------------------------------------
    async def embed(self, text: str, model: str = "text-embedding-ada-002") -> Dict[str, Any]:
        """Return embedding vector from LM Studio or fallback."""
        client = await self._get_client()
        try:
            r = await client.post(f"{self.lmstudio_base}/embeddings", json={"model": model, "input": text})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -------------------------------------------------
    # Stream Responses (Generator)
    # -------------------------------------------------
    async def stream_complete(self, prompt: str, model: str = "gpt-3.5-turbo", temperature: float = 0.7):
        """
        Yield incremental tokens from LM Studio stream API if supported.
        """
        client = await self._get_client()
        url = f"{self.lmstudio_base}/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": True}
        try:
            async with client.stream("POST", url, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        yield line[5:].strip()
        except Exception as e:
            yield json.dumps({"error": str(e)})
