# comfyvn/modules/comfy_bridge.py
# ⚙️ 3. Server Core Production Chat — ComfyUI Bridge

import json
import requests
import time

class ComfyUIBridge:
    """Handles all communications with ComfyUI REST API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url.rstrip("/")

    def _safe_request(self, endpoint: str, payload: dict = None, method: str = "POST"):
        """Safely perform REST calls and handle errors."""
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            if method.upper() == "POST":
                response = requests.post(url, json=payload, timeout=10)
            else:
                response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "mock": True}

    def get_workflows(self):
        """List available ComfyUI workflows."""
        return self._safe_request("workflows", method="GET")

    def queue_render(self, prompt_text: str, output_path: str = "./outputs/latest.png"):
        """
        Sends a render request to ComfyUI based on a text prompt.
        You can later expand this to use predefined workflow templates.
        """
        payload = {
            "prompt": {
                "1": {
                    "inputs": {
                        "text": prompt_text,
                        "seed": 42
                    },
                    "class_type": "CLIPTextEncode"
                }
            },
            "output": output_path
        }

        return self._safe_request("prompt", payload)

    def poll_result(self, job_id: str, interval: float = 1.0, timeout: float = 15.0):
        """Polls ComfyUI for job completion."""
        start = time.time()
        while time.time() - start < timeout:
            res = self._safe_request(f"history/{job_id}", method="GET")
            if "error" not in res and res.get("status") == "complete":
                return res
            time.sleep(interval)
        return {"status": "timeout", "job_id": job_id}
