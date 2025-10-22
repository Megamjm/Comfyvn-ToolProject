from __future__ import annotations

"""Web packager for Mini-VN playable bundles."""

import json
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from comfyvn.core.content_filter import NSFW_KEYWORDS
from comfyvn.exporters.publish_common import (
    DeterministicZipBuilder,
    PackageOptions,
    append_json_log,
    diff_binary,
    diff_text,
    ensure_publish_root,
    hooks_payload,
    package_slug,
    sha256_bytes,
    slugify,
    write_json,
)
from comfyvn.exporters.renpy_orchestrator import DiffEntry, ExportResult
from comfyvn.obs.structlog_adapter import get_logger

LOGGER = get_logger("export.publish.web", component="export.publish", target="web")
LOG_PATH = Path("logs/export/publish.log")
DEFAULT_STYLES = (
    "body{margin:0;font-family:'Inter',system-ui,-apple-system,sans-serif;"
    "background:#0f172a;color:#e2e8f0;}"
    "main{max-width:960px;margin:0 auto;padding:3rem 1.5rem 6rem 1.5rem;}"
    "header{display:flex;flex-direction:column;gap:0.25rem;margin-bottom:2rem;}"
    "h1{margin:0;font-size:2.5rem;font-weight:600;}"
    "p.subtitle{margin:0;color:#94a3b8;}"
    "section{margin-bottom:2rem;padding:1.5rem;border-radius:1rem;background:#1e293b;"
    "box-shadow:0 20px 25px -15px rgba(15,23,42,.45);}"
    "section h2{margin-top:0;margin-bottom:1rem;font-size:1.1rem;color:#38bdf8;text-transform:uppercase;letter-spacing:.08em;}"
    "code,pre{font-family:'Fira Code','JetBrains Mono',monospace;background:#0f172a;"
    "border-radius:0.75rem;padding:1rem;display:block;overflow:auto;max-height:480px;}"
    "ul.asset-list{margin:0;padding-left:1.5rem;color:#cbd5f5;}"
    "li.asset{margin-bottom:0.35rem;}"
    ".status{display:inline-flex;align-items:center;gap:0.35rem;padding:0.25rem 0.75rem;"
    "border-radius:999px;font-size:0.85rem;font-weight:600;text-transform:uppercase;}"
    ".status.ok{background:rgba(34,197,94,.14);color:#22c55e;}"
    ".status.degraded{background:rgba(251,191,36,.14);color:#fbbf24;}"
    ".status.alert{background:rgba(248,113,113,.16);color:#f87171;}"
    ".watermark{position:fixed;top:10%;left:50%;transform:translateX(-50%) rotate(-18deg);"
    "font-size:3rem;font-weight:700;color:rgba(148,163,184,.14);pointer-events:none;z-index:10;"
    "letter-spacing:.4rem;text-transform:uppercase;}"
)


@dataclass
class WebRedactionOptions:
    strip_nsfw: bool = False
    watermark_text: Optional[str] = None
    remove_provenance: bool = False
    exclude_paths: Tuple[str, ...] = ()


@dataclass
class WebAssetRecord:
    kind: str
    alias: str
    relpath: str
    source: Path
    bundle_path: str
    digest: str
    metadata: Dict[str, Any]
    nsfw: bool = False


@dataclass
class WebPackageResult:
    target: str
    slug: str
    label: str
    version: Optional[str]
    archive_path: Optional[Path]
    manifest_path: Path
    content_map_path: Path
    preview_path: Path
    redaction_path: Path
    checksum: Optional[str]
    dry_run: bool
    diffs: List[DiffEntry] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)
    content_map: Dict[str, Any] = field(default_factory=dict)
    preview: Dict[str, Any] = field(default_factory=dict)
    redaction: Dict[str, Any] = field(default_factory=dict)
    hooks_path: Optional[Path] = None


def build(
    export_result: ExportResult,
    options: PackageOptions,
    *,
    redaction: Optional[WebRedactionOptions] = None,
) -> WebPackageResult:
    redaction = redaction or WebRedactionOptions()
    publish_root = ensure_publish_root(options.publish_root.expanduser().resolve())
    target_root = ensure_publish_root(publish_root / "web")

    label = (
        options.label
        or export_result.manifest_payload.get("project", {}).get("title")
        or export_result.project_id
    )
    slug = package_slug(export_result.project_id, label, options.version, "web")

    archive_path = target_root / f"{slug}.web.zip"
    manifest_path = target_root / f"{slug}.web.manifest.json"
    content_map_path = target_root / f"{slug}.web.content_map.json"
    preview_path = target_root / f"{slug}.web.preview.json"
    redaction_path = target_root / f"{slug}.web.redaction.json"
    hooks_path = target_root / f"{slug}.web.hooks.json"

    included_assets, removed_assets = _collect_assets(export_result, redaction)
    manifest_payload = _build_manifest(
        export_result,
        slug=slug,
        label=label,
        options=options,
        included_assets=included_assets,
        redaction=redaction,
        removed_assets=removed_assets,
    )
    content_map_payload = _build_content_map(
        export_result, included_assets, removed_assets
    )
    preview_payload = _build_preview(export_result, manifest_payload, removed_assets)

    redaction_payload = {
        "strip_nsfw": redaction.strip_nsfw,
        "removed_assets": [
            {
                "kind": asset.kind,
                "alias": asset.alias,
                "relpath": asset.relpath,
                "digest": asset.digest,
            }
            for asset in removed_assets
        ],
        "remove_provenance": redaction.remove_provenance,
        "watermark_text": redaction.watermark_text,
        "exclude_paths": list(redaction.exclude_paths),
    }

    builder = DeterministicZipBuilder()
    builder.add_bytes(
        f"{slug}/web/index.html",
        _render_index_html(
            label=label,
            version=options.version,
            watermark=redaction.watermark_text,
        ).encode("utf-8"),
    )
    builder.add_bytes(
        f"{slug}/web/styles/app.css",
        DEFAULT_STYLES.encode("utf-8"),
    )
    builder.add_bytes(
        f"{slug}/web/data/manifest.json",
        json.dumps(manifest_payload, indent=2, ensure_ascii=False).encode("utf-8"),
    )
    builder.add_bytes(
        f"{slug}/web/data/content_map.json",
        json.dumps(content_map_payload, indent=2, ensure_ascii=False).encode("utf-8"),
    )
    builder.add_bytes(
        f"{slug}/web/preview/health.json",
        json.dumps(preview_payload, indent=2, ensure_ascii=False).encode("utf-8"),
    )
    builder.add_bytes(
        f"{slug}/web/data/redaction.json",
        json.dumps(redaction_payload, indent=2, ensure_ascii=False).encode("utf-8"),
    )

    hooks_json: Optional[str] = None
    if options.include_debug:
        hooks = hooks_payload()
        hooks_json = json.dumps(hooks, indent=2, ensure_ascii=False)
        builder.add_bytes(
            f"{slug}/web/debug/modder_hooks.json", hooks_json.encode("utf-8")
        )

    for asset in included_assets:
        builder.add_file(f"{slug}/web/{asset.bundle_path}", asset.source, mode=0o644)

    archive_bytes = builder.build()
    checksum: Optional[str] = None
    archive_diff = diff_binary(archive_path, archive_bytes)

    manifest_json = json.dumps(manifest_payload, indent=2, ensure_ascii=False)
    content_map_json = json.dumps(content_map_payload, indent=2, ensure_ascii=False)
    preview_json = json.dumps(preview_payload, indent=2, ensure_ascii=False)
    redaction_json = json.dumps(redaction_payload, indent=2, ensure_ascii=False)

    manifest_diff = diff_text(manifest_path, manifest_json)
    content_map_diff = diff_text(content_map_path, content_map_json)
    preview_diff = diff_text(preview_path, preview_json)
    redaction_diff = diff_text(redaction_path, redaction_json)

    diffs: List[DiffEntry] = [
        archive_diff,
        manifest_diff,
        content_map_diff,
        preview_diff,
        redaction_diff,
    ]

    hooks_diff = None
    if hooks_json is not None:
        hooks_diff = diff_text(hooks_path, hooks_json)
        diffs.append(hooks_diff)

    if not options.dry_run:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(archive_bytes)
        checksum = sha256_bytes(archive_bytes)
        write_json(manifest_path, manifest_payload)
        write_json(content_map_path, content_map_payload)
        write_json(preview_path, preview_payload)
        write_json(redaction_path, redaction_payload)
        if hooks_json is not None:
            hooks_path.write_text(hooks_json, encoding="utf-8")
        append_json_log(
            LOG_PATH,
            {
                "target": "web",
                "slug": slug,
                "label": label,
                "version": options.version,
                "archive": archive_path.as_posix(),
                "checksum": checksum,
                "assets": len(included_assets),
                "removed_assets": len(removed_assets),
                "debug_hooks": bool(hooks_json),
            },
        )
        LOGGER.info(
            "Web package built slug=%s checksum=%s assets=%s removed=%s",
            slug,
            checksum,
            len(included_assets),
            len(removed_assets),
        )

    return WebPackageResult(
        target="web",
        slug=slug,
        label=label,
        version=options.version,
        archive_path=None if options.dry_run else archive_path,
        manifest_path=manifest_path,
        content_map_path=content_map_path,
        preview_path=preview_path,
        redaction_path=redaction_path,
        checksum=checksum,
        dry_run=options.dry_run,
        diffs=diffs,
        manifest=manifest_payload,
        content_map=content_map_payload,
        preview=preview_payload,
        redaction=redaction_payload,
        hooks_path=hooks_path if hooks_json is not None else None,
    )


def _collect_assets(
    export_result: ExportResult,
    redaction: WebRedactionOptions,
) -> Tuple[List[WebAssetRecord], List[WebAssetRecord]]:
    remove_map = set(_normalized_excludes(redaction.exclude_paths))
    included: List[WebAssetRecord] = []
    removed: List[WebAssetRecord] = []

    for usage in export_result.backgrounds.values():
        record = _make_asset_record("background", usage, redaction)
        if _should_redact(record, redaction, remove_map):
            removed.append(record)
        else:
            included.append(record)

    for usage in export_result.portraits.values():
        record = _make_asset_record("portrait", usage, redaction)
        if _should_redact(record, redaction, remove_map):
            removed.append(record)
        else:
            included.append(record)

    included.sort(key=lambda item: (item.kind, item.alias))
    removed.sort(key=lambda item: (item.kind, item.alias))
    return included, removed


def _normalized_excludes(paths: Iterable[str]) -> List[str]:
    output: List[str] = []
    for path in paths:
        value = str(path or "").strip()
        if not value:
            continue
        output.append(value.replace("\\", "/"))
    return output


def _make_asset_record(
    kind: str,
    usage: Any,
    redaction: WebRedactionOptions,
) -> WebAssetRecord:
    digest = usage.metadata.get("sha256") or _sha256_path(usage.source)
    alias_slug = slugify(usage.alias, fallback=f"{kind}")
    ext = usage.source.suffix.lower()
    bundle_name = f"assets/{digest[:12]}-{alias_slug}{ext}"
    metadata = dict(usage.metadata)
    extras = metadata.get("extras")
    if isinstance(extras, dict):
        metadata["extras"] = dict(extras)
    metadata = _sanitise_metadata(metadata, redaction.remove_provenance)
    nsfw = _asset_is_nsfw(metadata)
    return WebAssetRecord(
        kind=kind,
        alias=usage.alias,
        relpath=usage.relpath,
        source=usage.source,
        bundle_path=bundle_name,
        digest=digest,
        metadata=metadata,
        nsfw=nsfw,
    )


def _asset_is_nsfw(metadata: Dict[str, Any]) -> bool:
    extras = metadata.get("extras") or {}
    if isinstance(extras, dict):
        rating = str(extras.get("rating") or "").lower()
        if extras.get("nsfw") or rating in {"mature", "adult"}:
            return True
        tags = extras.get("tags")
        if isinstance(tags, (list, tuple, set)):
            for tag in tags:
                if isinstance(tag, str) and tag.lower() in NSFW_KEYWORDS:
                    return True
    return False


def _should_redact(
    record: WebAssetRecord,
    redaction: WebRedactionOptions,
    exclude_map: Iterable[str],
) -> bool:
    if redaction.strip_nsfw and record.nsfw:
        return True
    rel = record.relpath.replace("\\", "/")
    if rel in exclude_map:
        return True
    return False


def _build_manifest(
    export_result: ExportResult,
    *,
    slug: str,
    label: str,
    options: PackageOptions,
    included_assets: List[WebAssetRecord],
    removed_assets: List[WebAssetRecord],
    redaction: WebRedactionOptions,
) -> Dict[str, Any]:
    project = dict(export_result.manifest_payload.get("project") or {})
    timeline = dict(export_result.manifest_payload.get("timeline") or {})
    if redaction.remove_provenance:
        project.pop("source", None)
        timeline.pop("source", None)

    asset_catalog = [
        {
            "alias": asset.alias,
            "kind": asset.kind,
            "bundle_path": asset.bundle_path,
            "digest": asset.digest,
            "relpath": asset.relpath,
            "metadata": asset.metadata,
        }
        for asset in included_assets
    ]
    removed_catalog = [
        {
            "alias": asset.alias,
            "kind": asset.kind,
            "relpath": asset.relpath,
            "digest": asset.digest,
        }
        for asset in removed_assets
    ]

    try:
        script_manifest = export_result.manifest_path.relative_to(
            export_result.output_dir
        ).as_posix()
    except ValueError:
        script_manifest = export_result.manifest_path.as_posix()

    payload: Dict[str, Any] = {
        "target": "web",
        "slug": slug,
        "label": label,
        "version": options.version,
        "project": project,
        "timeline": timeline,
        "generated_at": export_result.generated_at,
        "script_manifest": script_manifest,
        "rating": export_result.manifest_payload.get("rating"),
        "gate": export_result.manifest_payload.get("gate"),
        "pov": export_result.manifest_payload.get("pov"),
        "worlds": export_result.manifest_payload.get("worlds"),
        "asset_catalog": asset_catalog,
        "removed_assets": removed_catalog,
        "missing_assets": export_result.manifest_payload.get("missing_assets"),
        "redaction": {
            "strip_nsfw": redaction.strip_nsfw,
            "remove_provenance": redaction.remove_provenance,
            "watermark_text": redaction.watermark_text,
        },
        "include_debug": options.include_debug,
        "api_endpoints": [
            "/api/publish/web/build",
            "/api/publish/web/redact",
            "/api/publish/web/preview",
        ],
    }
    if not redaction.remove_provenance and options.provenance_inputs:
        payload["provenance_inputs"] = dict(options.provenance_inputs)
    return payload


def _build_content_map(
    export_result: ExportResult,
    included_assets: List[WebAssetRecord],
    removed_assets: List[WebAssetRecord],
) -> Dict[str, Any]:
    scenes = []
    for entry in export_result.label_map:
        scenes.append(
            {
                "scene_id": entry.get("scene_id"),
                "label": entry.get("label"),
                "title": entry.get("title"),
                "source": entry.get("source"),
                "pov": entry.get("pov_ids") or [],
            }
        )
    asset_map = {
        "backgrounds": [
            {
                "alias": asset.alias,
                "bundle_path": asset.bundle_path,
                "digest": asset.digest,
            }
            for asset in included_assets
            if asset.kind == "background"
        ],
        "portraits": [
            {
                "alias": asset.alias,
                "bundle_path": asset.bundle_path,
                "digest": asset.digest,
            }
            for asset in included_assets
            if asset.kind == "portrait"
        ],
    }
    removed_map = [
        {
            "alias": asset.alias,
            "kind": asset.kind,
            "relpath": asset.relpath,
        }
        for asset in removed_assets
    ]
    return {
        "scenes": scenes,
        "asset_map": asset_map,
        "removed_assets": removed_map,
        "pov": export_result.manifest_payload.get("pov"),
        "worlds": export_result.manifest_payload.get("worlds"),
        "rating": export_result.manifest_payload.get("rating"),
        "missing_assets": export_result.manifest_payload.get("missing_assets"),
    }


def _build_preview(
    export_result: ExportResult,
    manifest_payload: Dict[str, Any],
    removed_assets: List[WebAssetRecord],
) -> Dict[str, Any]:
    missing = export_result.manifest_payload.get("missing_assets") or {}
    status = "ok"
    if removed_assets or any(missing.values()):
        status = "degraded"
    return {
        "status": status,
        "generated_at": export_result.generated_at,
        "removed_assets": len(removed_assets),
        "missing_assets": missing,
        "pov_routes": manifest_payload.get("pov"),
        "worlds": manifest_payload.get("worlds"),
    }


def _render_index_html(
    *,
    label: str,
    version: Optional[str],
    watermark: Optional[str],
) -> str:
    safe_label = html_escape(label)
    version_badge = (
        f'<span class="status ok">Version {html_escape(version)}</span>'
        if version
        else ""
    )
    watermark_block = ""
    if watermark:
        watermark_block = f'<div class="watermark">{html_escape(watermark)}</div>'
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{safe_label} — ComfyVN Web Preview</title>"
        '<link rel="stylesheet" href="./styles/app.css">'
        "</head><body>"
        f"{watermark_block}"
        "<main>"
        "<header>"
        f"<h1>{safe_label}</h1>"
        '<p class="subtitle">Mini-VN redacted preview bundle</p>'
        f"{version_badge}"
        "</header>"
        "<section>"
        "<h2>Bundle Overview</h2>"
        '<div id="bundle-summary"><p>Loading manifest…</p></div>'
        "</section>"
        "<section>"
        "<h2>Assets</h2>"
        '<ul class="asset-list" id="asset-list"></ul>'
        "</section>"
        "<section>"
        "<h2>Content Map</h2>"
        '<pre id="content-map">Loading…</pre>'
        "</section>"
        "</main>"
        '<script type="module">'
        "async function main(){"
        "const manifest=await fetch('./data/manifest.json').then(r=>r.json());"
        "const content=await fetch('./data/content_map.json').then(r=>r.json());"
        "const summary=document.getElementById('bundle-summary');"
        "const list=document.getElementById('asset-list');"
        "const map=document.getElementById('content-map');"
        "summary.innerHTML='';"
        "const summaryPre=document.createElement('pre');"
        "summaryPre.textContent=JSON.stringify({slug:manifest.slug,label:manifest.label,"
        "version:manifest.version,redaction:manifest.redaction},null,2);"
        "summary.appendChild(summaryPre);"
        "list.innerHTML='';"
        "for(const asset of manifest.asset_catalog||[]){"
        "const li=document.createElement('li');"
        "li.className='asset';"
        "li.textContent=`${asset.kind}: ${asset.alias} → ${asset.bundle_path}`;"
        "list.appendChild(li);}"
        "map.textContent=JSON.stringify(content,null,2);"
        "}"
        "main().catch(err=>{"
        "const summary=document.getElementById('bundle-summary');"
        "summary.innerHTML='<p class=\"status alert\">Failed to load preview</p>';"
        "console.error(err);});"
        "</script>"
        "</body></html>"
    )


def _sanitise_metadata(
    metadata: Dict[str, Any],
    remove_provenance: bool,
) -> Dict[str, Any]:
    if not remove_provenance:
        return metadata
    metadata.pop("seed", None)
    metadata.pop("workflow_id", None)
    metadata.pop("workflow_hash", None)
    extras = metadata.get("extras")
    if isinstance(extras, dict):
        for key in ["provenance", "workflow", "source_hash", "seed"]:
            extras.pop(key, None)
    return metadata


def _sha256_path(path: Path) -> str:
    data = path.read_bytes()
    return sha256_bytes(data)


__all__ = ["WebRedactionOptions", "WebPackageResult", "build"]
