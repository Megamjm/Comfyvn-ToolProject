# comfyvn/core/event_bridge.py
# 🌐 Playground Event Bridge (GUI → Server)
# Sends broadcast updates to /playground/notify
# [ComfyVN_Architect | Phase 3.8-G]

import json, threading, requests


class EventBridge:
    """Lightweight async broadcaster from GUI → Server Core."""

    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def send(self, event_type: str, data: dict):
        """Send event asynchronously."""

        def _work():
            try:
                requests.post(
                    f"{self.base_url}/playground/notify",
                    json={"type": event_type, "data": data},
                    timeout=3,
                )
            except Exception as e:
                print(f"[EventBridge] ⚠️ Failed broadcast: {e}")

        threading.Thread(target=_work, daemon=True).start()
