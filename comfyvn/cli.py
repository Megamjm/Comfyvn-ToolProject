from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer

from comfyvn.assets_manifest import build_manifest
from comfyvn.logging_setup import init_logging
from comfyvn.lmstudio_client import healthcheck
from comfyvn.scene_bundle import convert_file as bundle_convert
from comfyvn.sdk import ComfyVN

app = typer.Typer(add_completion=False, help="ComfyVN command line utilities.")
logger = logging.getLogger(__name__)


@app.command()
def login(url: str, email: str, password: str) -> None:
    """Authenticate with a ComfyVN server."""
    init_logging("login")
    logger.info("Authenticating against %s", url)
    client = ComfyVN(url)
    print(client.login(email, password))


@app.command()
def scenes(url: str, token: str) -> None:
    """List scenes from a ComfyVN server."""
    init_logging("scenes")
    logger.info("Listing scenes from %s", url)
    client = ComfyVN(url, token)
    print(json.dumps(client.scene_list(), indent=2))


@app.command()
def check() -> None:
    """Run LM Studio healthcheck and log the run."""
    init_logging("check")
    status = healthcheck()
    logger.info("LM Studio health: %s", status.get("status", status))
    print(json.dumps(status, indent=2))
    raise SystemExit(0 if status.get("ok") else 1)


@app.command()
def manifest(
    assets: Path = typer.Option(Path("assets"), help="Assets root directory."),
    out: Optional[Path] = typer.Option(None, help="Manifest output file."),
) -> None:
    """Build the asset manifest for the project."""
    init_logging("manifest")
    logger.info("Building manifest for %s", assets)
    manifest_data = build_manifest(str(assets), str(out) if out else None)
    result = {
        "ok": True,
        "count": manifest_data["count"],
        "out": str(out or (assets / "assets.manifest.json")),
    }
    print(json.dumps(result, indent=2))


@app.command()
def bundle(
    raw: Path = typer.Option(..., help="Path to raw scene JSON exported from SillyTavern"),
    manifest: Path = typer.Option(Path("assets/assets.manifest.json"), help="Assets manifest path"),
    schema: Path = typer.Option(Path("docs/scene_bundle.schema.json"), help="Bundle schema path"),
    out: Optional[Path] = typer.Option(None, help="Override bundle output path"),
    name: Optional[str] = typer.Option(None, help="Override bundle filename stem"),
) -> None:
    """Convert a raw SillyTavern export into a Scene Bundle."""
    init_logging("bundle")
    target = out or Path("bundles") / f"{name or raw.stem}.bundle.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Converting raw scene %s -> %s", raw, target)
    bundle_data = bundle_convert(str(raw), str(target), manifest_path=str(manifest), schema_path=str(schema))
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(target),
                "id": bundle_data.get("id"),
                "characters": [c["name"] for c in bundle_data.get("characters", [])],
            },
            indent=2,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
