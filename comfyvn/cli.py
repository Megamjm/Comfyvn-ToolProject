from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from comfyvn.assets_manifest import build_manifest
from comfyvn.logging_setup import init_logging
from comfyvn.lmstudio_client import healthcheck
from comfyvn.sdk import ComfyVN

app = typer.Typer(add_completion=False, help="ComfyVN command line utilities.")


@app.command()
def login(url: str, email: str, password: str) -> None:
    """Authenticate with a ComfyVN server."""
    client = ComfyVN(url)
    print(client.login(email, password))


@app.command()
def scenes(url: str, token: str) -> None:
    """List scenes from a ComfyVN server."""
    client = ComfyVN(url, token)
    print(json.dumps(client.scene_list(), indent=2))


@app.command()
def check() -> None:
    """Run LM Studio healthcheck and log the run."""
    init_logging("check")
    status = healthcheck()
    print(json.dumps(status, indent=2))
    raise SystemExit(0 if status.get("ok") else 1)


@app.command()
def manifest(
    assets: Path = typer.Option(Path("assets"), help="Assets root directory."),
    out: Optional[Path] = typer.Option(None, help="Manifest output file."),
) -> None:
    """Build the asset manifest for the project."""
    init_logging("manifest")
    manifest_data = build_manifest(str(assets), str(out) if out else None)
    result = {
        "ok": True,
        "count": manifest_data["count"],
        "out": str(out or (assets / "assets.manifest.json")),
    }
    print(json.dumps(result, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
