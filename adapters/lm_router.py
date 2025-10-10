from __future__ import annotations
import os, requests

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "sk-local")
LLM_MODEL = os.environ.get("LLM_MODEL", "local")

def complete(prompt:str, max_tokens:int=512, temperature:float=0.6) -> str:
    url = f"{LLM_ENDPOINT}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type":"application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [{"role":"user","content":prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"]
