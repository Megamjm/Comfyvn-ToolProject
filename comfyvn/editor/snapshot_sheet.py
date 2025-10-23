from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, field_validator

from comfyvn.config.runtime_paths import cache_dir
from comfyvn.core import modder_hooks
from comfyvn.core.modder_hooks import HookSpec

LOGGER = logging.getLogger(__name__)

_DEFAULT_ROOT = Path(os.getenv("COMFYVN_EXPORT_ROOT", "exports")).resolve()


def _ensure_hook() -> None:
    if "on_snapshot_sheet_rendered" in modder_hooks.HOOK_SPECS:
        return
    spec = HookSpec(
        name="on_snapshot_sheet_rendered",
        description="Emitted when the snapshot sheet compositor writes a PNG/PDF board.",
        payload_fields={
            "sheet_id": "Deterministic identifier derived from payload digest.",
            "digest": "SHA-1 digest of the request payload used to build the sheet.",
            "outputs": "List of generated artefacts with format and filesystem path.",
            "project_id": "Optional project identifier supplied by the caller.",
            "timeline_id": "Optional timeline identifier supplied by the caller.",
            "item_count": "Number of snapshot tiles rendered.",
            "timestamp": "Event emission timestamp (UTC seconds).",
        },
        ws_topic="editor.snapshot_sheet.rendered",
        rest_event="on_snapshot_sheet_rendered",
    )
    modder_hooks.HOOK_SPECS[spec.name] = spec
    bus = getattr(modder_hooks, "_BUS", None)
    if bus and getattr(bus, "_listeners", None) is not None:
        with bus._lock:  # type: ignore[attr-defined]
            bus._listeners.setdefault(spec.name, [])  # type: ignore[attr-defined]


def _slugify(value: Any, default: str = "snapshot") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
    safe = safe.strip("_") or default
    return safe


def _color_tuple(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not value:
        return fallback
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    try:
        if len(text) == 6:
            r = int(text[0:2], 16)
            g = int(text[2:4], 16)
            b = int(text[4:6], 16)
            return (r, g, b)
        if len(text) == 3:
            r = int(text[0] * 2, 16)
            g = int(text[1] * 2, 16)
            b = int(text[2] * 2, 16)
            return (r, g, b)
    except ValueError:
        pass
    return fallback


def _default_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:  # pragma: no cover - optional font
        return ImageFont.load_default()


def _sheet_output_dir() -> Path:
    root = _DEFAULT_ROOT
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    sheet_dir = root / "snapshot_sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    return sheet_dir


class SnapshotSheetItem(BaseModel):
    id: str | None = None
    node_id: str | None = None
    snapshot_id: str | None = None
    image: str | None = None
    thumbnail: dict[str, Any] | None = None
    caption: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class SnapshotSheetLayout(BaseModel):
    columns: int = Field(default=3, ge=1, le=6)
    rows: int | None = Field(default=None, ge=1, le=6)
    cell_width: int = Field(default=512, ge=128, le=1920)
    cell_height: int = Field(default=288, ge=128, le=1080)
    margin: int = Field(default=48, ge=0, le=256)
    padding: int = Field(default=24, ge=0, le=128)
    caption_height: int = Field(default=72, ge=24, le=256)
    header_height: int = Field(default=96, ge=0, le=256)
    background: str = "#101010"
    caption_color: str = "#f1f1f1"
    font_size: int = Field(default=20, ge=8, le=48)

    model_config = ConfigDict(extra="ignore")


class SnapshotSheetRequest(BaseModel):
    items: List[SnapshotSheetItem]
    project_id: str | None = None
    timeline_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    seed: int | None = None
    layout: SnapshotSheetLayout = Field(default_factory=SnapshotSheetLayout)
    outputs: List[str] = Field(default_factory=lambda: ["png"])
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    @field_validator("outputs", mode="before")
    def _coerce_outputs(cls, value: Any) -> List[str]:
        if value is None:
            return ["png"]
        if isinstance(value, str):
            return [value.lower()]
        if isinstance(value, Iterable):
            out: List[str] = []
            for entry in value:
                if not entry:
                    continue
                out.append(str(entry).lower())
            return out or ["png"]
        return ["png"]


class SnapshotSheetResult(BaseModel):
    sheet_id: str
    digest: str
    outputs: List[dict[str, Any]]
    items: List[dict[str, Any]]
    layout: dict[str, Any]
    context: dict[str, Any]

    model_config = ConfigDict(extra="ignore")


@dataclass
class _PreparedItem:
    source: SnapshotSheetItem
    image: Image.Image
    caption: str
    path: str | None
    missing: bool


class SnapshotSheetBuilder:
    """Compose deterministic snapshot contact sheets for review and sharing."""

    def __init__(self) -> None:
        _ensure_hook()

    def render(self, request: SnapshotSheetRequest) -> SnapshotSheetResult:
        if not request.items:
            raise ValueError(
                "SnapshotSheetRequest.items must contain at least one entry"
            )

        digest = self._digest(request)
        sheet_id = f"sheet-{digest[:10]}"

        prepared = [self._prepare_item(item, request.layout) for item in request.items]
        layout = request.layout
        columns = layout.columns
        rows = layout.rows or math.ceil(len(prepared) / columns)

        width = (
            layout.margin * 2
            + columns * layout.cell_width
            + (columns - 1) * layout.padding
        )
        height = (
            layout.margin * 2
            + layout.header_height
            + rows * (layout.cell_height + layout.caption_height)
            + max(rows - 1, 0) * layout.padding
        )

        background = _color_tuple(layout.background, (16, 16, 16))
        caption_color = _color_tuple(layout.caption_color, (240, 240, 240))

        sheet = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(sheet)

        header_font = _default_font(layout.font_size + 8)
        caption_font = _default_font(layout.font_size)

        cursor_y = layout.margin
        if request.title:
            draw.text(
                (layout.margin, cursor_y),
                request.title,
                fill=caption_color,
                font=header_font,
            )
            cursor_y += header_font.getbbox(request.title)[3] + 4
        if request.subtitle:
            draw.text(
                (layout.margin, cursor_y),
                request.subtitle,
                fill=caption_color,
                font=caption_font,
            )
        cursor_y = layout.margin + layout.header_height

        for index, prepared_item in enumerate(prepared):
            col = index % columns
            row = index // columns
            origin_x = layout.margin + col * (layout.cell_width + layout.padding)
            origin_y = cursor_y + row * (
                layout.cell_height + layout.caption_height + layout.padding
            )

            tile = self._fit_image(
                prepared_item.image, layout.cell_width, layout.cell_height
            )
            offset_x = origin_x + (layout.cell_width - tile.width) // 2
            offset_y = origin_y + (layout.cell_height - tile.height) // 2
            sheet.paste(tile, (offset_x, offset_y))

            wrap_width = max(20, layout.cell_width // 12)
            caption_text = prepared_item.caption or "Snapshot"
            if prepared_item.missing:
                caption_text = f"[missing] {caption_text}"
            wrapped = textwrap.fill(caption_text, width=wrap_width)
            caption_y = origin_y + layout.cell_height + 6
            draw.multiline_text(
                (origin_x, caption_y),
                wrapped,
                fill=caption_color,
                font=caption_font,
                spacing=4,
            )

        output_dir = _sheet_output_dir()
        outputs: List[dict[str, Any]] = []
        base_metadata = {
            "sheet_id": sheet_id,
            "digest": digest,
            "width": width,
            "height": height,
        }

        if "png" in request.outputs:
            png_path = output_dir / f"{sheet_id}.png"
            sheet.save(png_path, format="PNG")
            outputs.append(
                {**base_metadata, "format": "png", "path": png_path.as_posix()}
            )

        if "pdf" in request.outputs:
            pdf_path = output_dir / f"{sheet_id}.pdf"
            sheet.convert("RGB").save(pdf_path, format="PDF")
            outputs.append(
                {**base_metadata, "format": "pdf", "path": pdf_path.as_posix()}
            )

        items_payload = [
            {
                "id": prepared_item.source.id or prepared_item.source.snapshot_id,
                "node_id": prepared_item.source.node_id,
                "caption": prepared_item.caption,
                "path": prepared_item.path,
                "missing": prepared_item.missing,
            }
            for prepared_item in prepared
        ]

        result_payload = {
            "sheet_id": sheet_id,
            "digest": digest,
            "outputs": outputs,
            "items": items_payload,
            "layout": layout.model_dump(mode="python"),
            "context": {
                "project_id": request.project_id,
                "timeline_id": request.timeline_id,
                "title": request.title,
                "subtitle": request.subtitle,
                "metadata": request.metadata,
            },
        }

        try:
            modder_hooks.emit(
                "on_snapshot_sheet_rendered",
                {
                    "sheet_id": sheet_id,
                    "digest": digest,
                    "outputs": outputs,
                    "project_id": request.project_id,
                    "timeline_id": request.timeline_id,
                    "item_count": len(prepared),
                    "timestamp": time.time(),
                },
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Snapshot sheet hook emission failed", exc_info=True)

        return SnapshotSheetResult.model_validate(result_payload)

    def _prepare_item(
        self, item: SnapshotSheetItem, layout: SnapshotSheetLayout
    ) -> _PreparedItem:
        caption = item.caption or item.metadata.get("caption")
        if not caption:
            caption = (
                (item.id or item.node_id or item.snapshot_id or "Snapshot")
                .replace("_", " ")
                .title()
            )

        path = self._resolve_path(item)
        if path and path.exists():
            try:
                image = Image.open(path).convert("RGB")
                return _PreparedItem(
                    source=item,
                    image=image,
                    caption=caption,
                    path=path.as_posix(),
                    missing=False,
                )
            except Exception:
                LOGGER.debug("Failed to open snapshot image %s", path, exc_info=True)

        placeholder = self._placeholder(layout)
        return _PreparedItem(
            source=item,
            image=placeholder,
            caption=caption,
            path=path.as_posix() if path else None,
            missing=True,
        )

    def _resolve_path(self, item: SnapshotSheetItem) -> Optional[Path]:
        candidates: List[Path] = []

        def _add(path: Optional[Path]) -> None:
            if path is None:
                return
            candidates.append(path)

        if item.image:
            path = Path(item.image)
            if not path.is_absolute():
                path = Path.cwd() / path
            _add(path)

        thumb = item.thumbnail or item.metadata.get("thumbnail")
        if isinstance(thumb, Mapping):
            path_raw = thumb.get("path")
            if isinstance(path_raw, str):
                _add(Path(path_raw))
            filename = thumb.get("filename")
            if isinstance(filename, str):
                _add(cache_dir("viewer", "thumbnails") / filename)

        for key in (item.snapshot_id, item.node_id, item.id):
            if not key:
                continue
            slug = _slugify(key)
            _add(cache_dir("viewer", "thumbnails") / f"{slug}.png")

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if candidates else None

    def _placeholder(self, layout: SnapshotSheetLayout) -> Image.Image:
        image = Image.new(
            "RGB",
            (layout.cell_width, layout.cell_height),
            _color_tuple("#1f1f1f", (31, 31, 31)),
        )
        draw = ImageDraw.Draw(image)
        font = _default_font(layout.font_size)
        text = "snapshot missing"
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        draw.text(
            ((layout.cell_width - width) // 2, (layout.cell_height - height) // 2),
            text,
            fill=_color_tuple("#555555", (85, 85, 85)),
            font=font,
        )
        return image

    def _fit_image(
        self, image: Image.Image, max_width: int, max_height: int
    ) -> Image.Image:
        width, height = image.size
        ratio = min(max_width / width, max_height / height, 1.0)
        new_size = (max(int(width * ratio), 1), max(int(height * ratio), 1))
        if new_size == image.size:
            return image.copy()
        return image.resize(new_size, Image.LANCZOS)

    def _digest(self, request: SnapshotSheetRequest) -> str:
        payload = {
            "items": [
                item.model_dump(
                    mode="python",
                    exclude_none=True,
                )
                for item in request.items
            ],
            "layout": request.layout.model_dump(mode="python"),
            "project_id": request.project_id,
            "timeline_id": request.timeline_id,
            "title": request.title,
            "subtitle": request.subtitle,
            "outputs": sorted(request.outputs),
            "metadata": request.metadata,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()


__all__ = [
    "SnapshotSheetBuilder",
    "SnapshotSheetItem",
    "SnapshotSheetLayout",
    "SnapshotSheetRequest",
    "SnapshotSheetResult",
]
