from PySide6.QtGui import QAction
import os, json, time, uuid, asyncio
from typing import Dict, Tuple, Optional, Callable, Any
import httpx
try:
    import websockets  # optional
except Exception:
    websockets = None

def _ws_url(http_url: str) -> str:
    # http://host:8188 -> ws://host:8188
    return ("ws" + http_url[4:]).rstrip("/") + "/ws?client_id=" + uuid.uuid4().hex

class ComfyUIClient:
    def __init__(self, api_base: str, timeout: float = 45.0):
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def ping(self) -> bool:
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(self.api_base + "/system_stats")
                return r.status_code == 200
        except Exception:
            return False

    def submit_and_track(self, workflow: Dict[str, Any], on_progress: Optional[Callable[[float, Dict[str, Any]], None]] = None) -> Tuple[Optional[bytes], Dict[str, Any]]:
        # Submit the workflow. Attempt WS progress and poll /history for images.
        client_id = uuid.uuid4().hex
        prompt_payload = {"client_id": client_id, **workflow}
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(self.api_base + "/prompt", json=prompt_payload)
                r.raise_for_status()
                resp = r.json()
        except Exception as e:
            return None, {"origin": "comfyui", "stage": "submit_error", "error": str(e)}

        prompt_id = resp.get("prompt_id") or resp.get("node_id") or resp.get("id")
        if not prompt_id:
            img = _extract_inline_image(resp)
            if img:
                if on_progress: on_progress(1.0, {"inline": True})
                return img, {"origin": "comfyui-inline"}
            return None, {"origin": "comfyui", "stage": "no_prompt_id"}

        # Try to open WS briefly for progress
        if websockets is not None:
            try:
                asyncio.get_event_loop().run_until_complete(self._ws_progress(on_progress))
            except RuntimeError:
                pass
            except Exception:
                pass

        # Poll /history for images
        deadline = time.time() + self.timeout
        last_p = 0.0
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=min(10, self.timeout)) as c:
                    r = c.get(f"{self.api_base}/history/{prompt_id}")
                    if r.status_code == 200:
                        hist = r.json()
                        img = _extract_history_image(hist, self.api_base)
                        if img:
                            if on_progress: on_progress(1.0, {"history": True})
                            return img, {"origin": "comfyui-history", "prompt_id": prompt_id}
            except Exception:
                pass
            last_p = min(0.99, last_p + 0.1)
            if on_progress: on_progress(last_p, {"poll": True})
            time.sleep(0.4)

        return None, {"origin": "comfyui", "stage": "timeout", "prompt_id": prompt_id}

    async def _ws_progress(self, on_progress):
        if websockets is None: return
        url = _ws_url(self.api_base)
        try:
            async with websockets.connect(url, ping_interval=None) as ws:
                for _ in range(10):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        if on_progress: on_progress(0.1, {"ws": True, "msg": str(msg)[:200]})
                    except asyncio.TimeoutError:
                        break
        except Exception:
            pass

def _extract_inline_image(obj: Dict[str, Any]) -> Optional[bytes]:
    import base64
    b64 = obj.get("image")
    if not b64 and isinstance(obj.get("images"), list) and obj["images"]:
        b64 = obj["images"][0].get("image")
    if b64:
        try: return base64.b64decode(b64.split(",")[-1])
        except Exception: return None
    return None

def _extract_history_image(hist: Dict[str, Any], api_base: str) -> Optional[bytes]:
    # Expect format: {'outputs': {'<node>': {'images':[{'filename':..., 'subfolder':'', 'type':'output'}]}}}
    try:
        outputs = hist.get("outputs") or {}
        for node, val in outputs.items():
            imgs = val.get("images") or []
            for im in imgs:
                fn = im.get("filename"); sub = im.get("subfolder",""); typ = im.get("type","output")
                if fn:
                    with httpx.Client(timeout=10) as c:
                        r = c.get(api_base.rstrip('/') + "/view", params={"filename": fn, "subfolder": sub, "type": typ})
                        if r.status_code == 200:
                            return r.content
    except Exception:
        return None
    return None