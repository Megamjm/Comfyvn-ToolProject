from PySide6.QtGui import QAction
# save as smoke_checks.py, run: python smoke_checks.py
import asyncio, json, sys
import httpx
import websockets

BASE = "http://localhost:8001"

def check_http():
    print("== HTTP checks ==")
    with httpx.Client(timeout=5) as c:
        for path in ["/limits/status", "/webhooks/list", "/auth/oidc/health", "/scheduler/health"]:
            try:
                r = c.get(BASE + path)
                print(f"{path} -> {r.status_code} {r.json() if 'application/json' in r.headers.get('content-type','') else r.text[:120]}")
            except Exception as e:
                print(f"{path} -> ERROR {e}")

async def check_ws():
    print("\n== Collab WebSocket check ==")
    url = "ws://localhost:8001/collab/ws?scene_id=dev"
    try:
        async with websockets.connect(url, ping_interval=None) as ws:
            # read server hello/presence
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            print("recv:", msg[:200])
            # ask for presence
            await ws.send(json.dumps({"type":"presence"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            print("presence:", msg[:200])
            # ping
            await ws.send(json.dumps({"type":"ping"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            print("pong:", msg[:200])
    except Exception as e:
        print("WS error:", e)

def main():
    check_http()
    try:
        asyncio.run(check_ws())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()