# comfyvn/server/app.py
# ⚙️ ComfyVN Server Entrypoint — Thin launcher (v4.0 Modular)
from __future__ import annotations
import asyncio, threading, os, uvicorn
from comfyvn.server.core.bootstrap import create_app


async def run_server(
    host: str = "127.0.0.1", port: int = 8001, log_level: str = "info"
):
    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level=log_level)
    server = uvicorn.Server(config)
    await server.serve()


def launch_server_thread(
    host: str = "127.0.0.1", port: int = 8001, log_level: str = "info"
):
    def _runner():
        asyncio.run(run_server(host, port, log_level))

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    host = os.getenv("COMFYVN_HOST", "0.0.0.0")
    port = int(os.getenv("COMFYVN_PORT", "8001"))
    asyncio.run(run_server(host, port))
