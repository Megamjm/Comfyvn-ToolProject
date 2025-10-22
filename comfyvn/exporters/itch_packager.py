from __future__ import annotations

"""itch.io packager."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from comfyvn.core import provenance
from comfyvn.obs.structlog_adapter import get_logger

from .publish_common import (
    DeterministicZipBuilder,
    PackageOptions,
    PackageResult,
    append_json_log,
    build_license_manifest,
    collect_game_files,
    diff_binary,
    diff_text,
    ensure_publish_root,
    hooks_payload,
    normalise_platforms,
    package_slug,
    resolve_eula_text,
    resolve_icon_bytes,
    resolve_license_text,
    sha256_bytes,
    write_json,
)
from .renpy_orchestrator import DiffEntry, ExportResult

LOGGER = get_logger("export.publish.itch", component="export.publish", target="itch")
LOG_PATH = Path("logs/export/publish.log")


def _channels(platforms: List[str], slug: str) -> List[Dict[str, Any]]:
    channels: List[Dict[str, Any]] = []
    for platform in platforms:
        channels.append(
            {
                "channel": f"{platform}-stable",
                "platform": platform,
                "artifact": f"{slug}/itch/builds/{platform}/game",
            }
        )
    return channels


def _package_manifest(
    export_result: ExportResult,
    *,
    slug: str,
    label: str,
    version: Optional[str],
    platforms: List[str],
    license_manifest: Dict[str, Any],
    options: PackageOptions,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "target": "itch",
        "slug": slug,
        "label": label,
        "version": version,
        "platforms": platforms,
        "channels": _channels(platforms, slug),
        "generated_at": export_result.generated_at,
        "project": export_result.manifest_payload.get("project"),
        "timeline": export_result.manifest_payload.get("timeline"),
        "worlds": export_result.manifest_payload.get("worlds"),
        "pov": export_result.manifest_payload.get("pov"),
        "assets": export_result.manifest_payload.get("assets"),
        "missing_assets": export_result.manifest_payload.get("missing_assets"),
        "script": {
            "path": export_result.script_path.as_posix(),
            "manifest": export_result.manifest_path.as_posix(),
            "labels": export_result.label_map,
        },
        "policy_gate": export_result.gate,
        "license_manifest": {"path": None, "count": license_manifest.get("count", 0)},
        "provenance_inputs": dict(options.provenance_inputs),
        "metadata_overrides": dict(options.metadata_overrides),
        "dry_run": options.dry_run,
        "include_debug": options.include_debug,
    }
    return payload


def package(export_result: ExportResult, options: PackageOptions) -> PackageResult:
    platforms = normalise_platforms(options.platforms)
    publish_root = ensure_publish_root(options.publish_root.expanduser().resolve())
    target_root = ensure_publish_root(publish_root / "itch")
    label = (
        options.label
        or export_result.manifest_payload.get("project", {}).get("title")
        or export_result.project_id
    )
    slug = package_slug(export_result.project_id, label, options.version, "itch")
    archive_path = target_root / f"{slug}.itch.zip"
    manifest_path = target_root / f"{slug}.itch.manifest.json"
    license_manifest_path = target_root / f"{slug}.itch.licenses.json"
    hooks_path = target_root / f"{slug}.itch.hooks.json"

    license_manifest = build_license_manifest(
        export_result.manifest_payload.get("assets", {})
    )
    package_manifest = _package_manifest(
        export_result,
        slug=slug,
        label=label,
        version=options.version,
        platforms=platforms,
        license_manifest=license_manifest,
        options=options,
    )

    builder = DeterministicZipBuilder()
    icon_bytes = resolve_icon_bytes(options)
    builder.add_bytes(f"{slug}/itch/assets/icon.png", icon_bytes)

    eula_text = resolve_eula_text(options, target="itch", label=label)
    builder.add_bytes(f"{slug}/itch/legal/EULA.txt", eula_text.encode("utf-8"))

    license_text = resolve_license_text(options, license_manifest)
    builder.add_bytes(f"{slug}/itch/legal/LICENSE.txt", license_text.encode("utf-8"))

    license_manifest_json = json.dumps(license_manifest, indent=2, ensure_ascii=False)
    builder.add_bytes(
        f"{slug}/itch/legal/license_manifest.json",
        license_manifest_json.encode("utf-8"),
    )

    package_manifest_json = json.dumps(package_manifest, indent=2, ensure_ascii=False)
    builder.add_bytes(
        f"{slug}/itch/publish_manifest.json", package_manifest_json.encode("utf-8")
    )
    builder.add_bytes(
        f"{slug}/itch/channels.json",
        json.dumps(_channels(platforms, slug), indent=2, ensure_ascii=False).encode(
            "utf-8"
        ),
    )

    butler_stub = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'echo "Butler upload placeholder for {label}" >&2\n'
        "echo \"Call 'butler push <build> <user>/<game>:<channel>' manually.\"\n"
    )
    builder.add_bytes(
        f"{slug}/itch/README_butler.sh", butler_stub.encode("utf-8"), mode=0o755
    )

    game_dir = export_result.output_dir / "game"
    files = collect_game_files(game_dir)
    if not files and not options.dry_run:
        raise FileNotFoundError(
            f"Ren'Py export output missing 'game' directory at {game_dir}"
        )
    for platform in platforms:
        for rel, source in files:
            arcname = f"{slug}/itch/builds/{platform}/game/{rel}"
            builder.add_file(arcname, source, mode=0o644)

    provenance_payload = {
        "tool": "comfyvn.export.publish",
        "target": "itch",
        "label": label,
        "version": options.version,
        "platforms": platforms,
        "generated_at": export_result.generated_at,
        "script_path": export_result.script_path.as_posix(),
        "manifest_path": export_result.manifest_path.as_posix(),
    }
    if options.provenance_inputs:
        provenance_payload["inputs"] = options.provenance_inputs
    builder.add_bytes(
        f"{slug}/itch/provenance.json",
        json.dumps(provenance_payload, indent=2, ensure_ascii=False).encode("utf-8"),
    )

    hooks_json = None
    if options.include_debug:
        hooks_json = json.dumps(hooks_payload(), indent=2, ensure_ascii=False)
        builder.add_bytes(
            f"{slug}/itch/debug/modder_hooks.json", hooks_json.encode("utf-8")
        )

    archive_bytes = builder.build()
    archive_diff = diff_binary(archive_path, archive_bytes)
    manifest_diff = diff_text(manifest_path, package_manifest_json)
    license_diff = diff_text(license_manifest_path, license_manifest_json)
    diffs: List[DiffEntry] = [archive_diff, manifest_diff, license_diff]

    hooks_diff = None
    if hooks_json is not None:
        hooks_diff = diff_text(hooks_path, hooks_json)
        diffs.append(hooks_diff)

    checksum: Optional[str] = None
    provenance_sidecars: Dict[str, Optional[str]] = {}

    if options.dry_run:
        LOGGER.info(
            "itch publish dry-run",
            slug=slug,
            platforms=platforms,
            archive_path=archive_path.as_posix(),
        )
        append_json_log(
            LOG_PATH,
            {
                "event": "itch_publish_dry_run",
                "slug": slug,
                "platforms": platforms,
                "archive_path": archive_path.as_posix(),
                "project": export_result.project_id,
                "timeline": export_result.timeline_id,
            },
        )
        return PackageResult(
            target="itch",
            label=label,
            version=options.version,
            archive_path=archive_path,
            manifest_path=manifest_path,
            license_manifest_path=license_manifest_path,
            checksum=None,
            dry_run=True,
            diffs=diffs,
            provenance_sidecars=provenance_sidecars,
            hooks_path=hooks_path.as_posix() if hooks_json is not None else None,
            manifest=package_manifest,
            license_manifest=license_manifest,
        )

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_bytes)
    write_json(manifest_path, package_manifest)
    write_json(license_manifest_path, license_manifest)
    if hooks_json is not None:
        write_json(hooks_path, json.loads(hooks_json))

    checksum = sha256_bytes(archive_bytes)
    archive_stamp = provenance.stamp_path(
        archive_path,
        source="export.publish.itch",
        inputs={
            "target": "itch",
            "label": label,
            "version": options.version,
            "platforms": platforms,
            "project": export_result.project_id,
            "timeline": export_result.timeline_id,
        },
        embed=False,
    )
    manifest_stamp = provenance.stamp_path(
        manifest_path,
        source="export.publish.itch.manifest",
        inputs={
            "target": "itch",
            "label": label,
            "version": options.version,
        },
        embed=False,
    )
    provenance_sidecars["archive"] = archive_stamp.get("sidecar_path")
    provenance_sidecars["manifest"] = manifest_stamp.get("sidecar_path")

    LOGGER.info(
        "itch publish package created",
        slug=slug,
        checksum=checksum,
        archive_path=archive_path.as_posix(),
    )
    append_json_log(
        LOG_PATH,
        {
            "event": "itch_publish_created",
            "slug": slug,
            "checksum": checksum,
            "archive_path": archive_path.as_posix(),
            "manifest_path": manifest_path.as_posix(),
            "project": export_result.project_id,
            "timeline": export_result.timeline_id,
        },
    )

    return PackageResult(
        target="itch",
        label=label,
        version=options.version,
        archive_path=archive_path,
        manifest_path=manifest_path,
        license_manifest_path=license_manifest_path,
        checksum=checksum,
        dry_run=False,
        diffs=diffs,
        provenance_sidecars=provenance_sidecars,
        hooks_path=hooks_path.as_posix() if hooks_json is not None else None,
        manifest=package_manifest,
        license_manifest=license_manifest,
    )


__all__ = ["package"]
