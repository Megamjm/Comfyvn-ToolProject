"""Provider registry and stage implementations for the manga pipeline."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional

import requests

try:
    from PIL import Image, UnidentifiedImageError
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    UnidentifiedImageError = Exception  # type: ignore

try:  # pragma: no cover - optional dependency
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import easyocr  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    easyocr = None  # type: ignore

from comfyvn.core.comfyui_client import ComfyUIClient

LOGGER = logging.getLogger(__name__)

StageKey = Literal["segment", "ocr", "group", "speaker"]
ProviderKind = Literal["open_source", "freemium", "paid"]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete its work."""


@dataclass(slots=True)
class StageContext:
    job_id: str
    stage: StageKey
    base_dir: Path
    raw_dir: Path
    ocr_dir: Path
    group_dir: Path
    scenes_dir: Path
    pages: List[Path]
    data: Dict[str, Any]
    log: Callable[[str], None]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StageResult:
    payload: Any
    artifacts: List[Path]
    notes: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ProviderMetadata:
    id: str
    stage: StageKey
    label: str
    kind: ProviderKind
    description: str
    default_settings: Dict[str, Any] = field(default_factory=dict)
    docs_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "stage": self.stage,
            "label": self.label,
            "kind": self.kind,
            "paid": self.kind == "paid",
            "description": self.description,
            "default_settings": self.default_settings,
            "tags": self.tags,
        }
        if self.docs_url:
            payload["docs_url"] = self.docs_url
        return payload


class StageProvider:
    """Base callable provider."""

    metadata: ProviderMetadata

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        raise NotImplementedError


class BasicSegmenter(StageProvider):
    metadata = ProviderMetadata(
        id="basic_panel",
        stage="segment",
        label="Full-page panel",
        kind="open_source",
        description=(
            "Treat each page as a single full-bleed panel. "
            "Useful as a fallback when no segmentation model is configured."
        ),
        tags=["fallback", "no-op"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        panels: List[Dict[str, Any]] = []
        artifacts: List[Path] = []
        for index, page in enumerate(ctx.pages, start=1):
            if not _is_image(page):
                ctx.log(f"Skipping non-image resource during segmentation: {page.name}")
                continue
            width, height = _probe_image_size(page)
            panels.append(
                {
                    "page": page.name,
                    "page_path": str(page),
                    "panel_id": f"{ctx.job_id}-panel-{index:03d}-001",
                    "bbox": [0, 0, width, height],
                    "normalized_bbox": [0.0, 0.0, 1.0, 1.0],
                    "confidence": 0.42,
                    "segments": [
                        {
                            "segment_id": f"{ctx.job_id}-segment-{index:03d}",
                            "bbox": [0, 0, width, height],
                            "normalized_bbox": [0.0, 0.0, 1.0, 1.0],
                        }
                    ],
                }
            )
        target = ctx.raw_dir / "panels.json"
        target.write_text(json.dumps(panels, indent=2), encoding="utf-8")
        artifacts.append(target)
        notes = [f"Segmented {len(panels)} pages with single-panel heuristic."]
        return StageResult(payload=panels, artifacts=artifacts, notes=notes)


class WhitespaceSegmenter(StageProvider):
    metadata = ProviderMetadata(
        id="whitespace_split",
        stage="segment",
        label="Whitespace splitter",
        kind="open_source",
        description=(
            "Detect horizontal whitespace bands to derive simple panel splits "
            "without requiring ML models. Works best on clean scan layouts."
        ),
        default_settings={"threshold": 245, "min_band_pct": 0.035},
        tags=["heuristic"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        if Image is None:
            raise ProviderError("Pillow is required for whitespace segmentation.")
        threshold = int(settings.get("threshold", 245))
        min_band_pct = float(settings.get("min_band_pct", 0.035))
        panels: List[Dict[str, Any]] = []
        notes: List[str] = []
        for page_index, page_path in enumerate(ctx.pages, start=1):
            if not _is_image(page_path):
                ctx.log(
                    f"Skipping non-image resource during segmentation: {page_path.name}"
                )
                continue
            image = Image.open(page_path).convert("L")
            width, height = image.size
            pixels = image.load()
            blank_rows: List[int] = []
            for y in range(height):
                light_pixels = sum(1 for x in range(width) if pixels[x, y] >= threshold)
                if light_pixels / max(width, 1) >= (1.0 - min_band_pct):
                    blank_rows.append(y)
            splits = _rows_to_segments(blank_rows, height)
            page_panels: List[Dict[str, Any]] = []
            if not splits:
                splits = [(0, height)]
            for seg_index, (start_y, end_y) in enumerate(splits, start=1):
                bbox = [0, start_y, width, end_y]
                normalized = [
                    0.0,
                    start_y / height if height else 0.0,
                    1.0,
                    end_y / height if height else 1.0,
                ]
                page_panels.append(
                    {
                        "panel_id": f"{ctx.job_id}-panel-{page_index:03d}-{seg_index:03d}",
                        "bbox": bbox,
                        "normalized_bbox": normalized,
                        "confidence": 0.6,
                    }
                )
            panels.append(
                {
                    "page": page_path.name,
                    "page_path": str(page_path),
                    "panels": page_panels,
                }
            )
            notes.append(
                f"{page_path.name}: detected {len(page_panels)} panels using whitespace heuristic."
            )
        target = ctx.raw_dir / "panels.json"
        target.write_text(json.dumps(panels, indent=2), encoding="utf-8")
        return StageResult(payload=panels, artifacts=[target], notes=notes)


class TesseractOCRProvider(StageProvider):
    metadata = ProviderMetadata(
        id="pytesseract",
        stage="ocr",
        label="Tesseract (local)",
        kind="open_source",
        description=(
            "Local Tesseract OCR via pytesseract. Requires Tesseract binary installed and "
            "available on PATH."
        ),
        default_settings={"lang": "eng"},
        docs_url="https://github.com/tesseract-ocr/tesseract",
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        if pytesseract is None or Image is None:
            raise ProviderError("pytesseract and Pillow are required for local OCR.")
        language = settings.get("lang", "eng")
        panels = ctx.data.get("panels") or []
        if not panels:
            notes = ["No panels available for OCR; skipping Tesseract run."]
            target = ctx.ocr_dir / "ocr_results.json"
            target.write_text("[]", encoding="utf-8")
            return StageResult(payload=[], artifacts=[target], notes=notes)
        results: List[Dict[str, Any]] = []
        notes: List[str] = []
        for page in panels:
            page_path = Path(page["page_path"])
            if not _is_image(page_path):
                ctx.log(f"Skipping OCR for non-image resource: {page_path.name}")
                continue
            image = Image.open(page_path)
            for panel in page.get("panels", []):
                bbox = panel.get("bbox") or [0, 0, image.width, image.height]
                crop = image.crop(tuple(bbox))
                text = pytesseract.image_to_string(crop, lang=language)
                cleaned = text.strip()
                results.append(
                    {
                        "panel_id": panel["panel_id"],
                        "page": page["page"],
                        "text": cleaned,
                        "provider": self.metadata.id,
                        "language": language,
                        "confidence": 0.65 if cleaned else 0.0,
                    }
                )
        target = ctx.ocr_dir / "ocr_results.json"
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        notes.append(f"OCR completed for {len(results)} panels via Tesseract.")
        return StageResult(payload=results, artifacts=[target], notes=notes)


class EasyOCROCRProvider(StageProvider):
    metadata = ProviderMetadata(
        id="easyocr",
        stage="ocr",
        label="EasyOCR (local)",
        kind="open_source",
        description="Local EasyOCR pipeline supporting multilingual recognition.",
        default_settings={"lang": ["en"]},
        docs_url="https://github.com/JaidedAI/EasyOCR",
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        if easyocr is None or Image is None:
            raise ProviderError("easyocr and Pillow are required for this provider.")
        languages = settings.get("lang") or ["en"]
        reader = easyocr.Reader(languages)  # type: ignore[arg-type]
        panels = ctx.data.get("panels") or []
        if not panels:
            target = ctx.ocr_dir / "ocr_results.json"
            target.write_text("[]", encoding="utf-8")
            return StageResult(
                payload=[],
                artifacts=[target],
                notes=["No panels available for OCR; skipping EasyOCR run."],
            )
        results: List[Dict[str, Any]] = []
        for page in panels:
            page_path = Path(page["page_path"])
            if not _is_image(page_path):
                ctx.log(f"Skipping OCR for non-image resource: {page_path.name}")
                continue
            image = Image.open(page_path)
            for panel in page.get("panels", []):
                bbox = panel.get("bbox") or [0, 0, image.width, image.height]
                crop = image.crop(tuple(bbox))
                temp_file = ctx.ocr_dir / f"tmp_{panel['panel_id']}.png"
                crop.save(temp_file)
                detections = reader.readtext(str(temp_file))
                text = " ".join(det[1] for det in detections)
                temp_file.unlink(missing_ok=True)
                results.append(
                    {
                        "panel_id": panel["panel_id"],
                        "page": page["page"],
                        "text": text.strip(),
                        "provider": self.metadata.id,
                        "language": languages,
                        "confidence": float(
                            max((det[2] for det in detections), default=0.6)
                        ),
                    }
                )
        target = ctx.ocr_dir / "ocr_results.json"
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return StageResult(
            payload=results,
            artifacts=[target],
            notes=[f"EasyOCR processed {len(results)} panels."],
        )


class ComfyUIOCRProvider(StageProvider):
    metadata = ProviderMetadata(
        id="comfyui_i2t",
        stage="ocr",
        label="ComfyUI workflow (I2T)",
        kind="open_source",
        description=(
            "Submit cropped panels to a ComfyUI workflow that emits recognized text. "
            "The workflow JSON must accept a base64 image placeholder ``{{image_base64}}`` "
            "and produce a text output node."
        ),
        default_settings={
            "base_url": "http://127.0.0.1:8188",
            "workflow": "workflows/ocr_i2t.json",
            "timeout": 180,
            "prompt_input": "{{image_base64}}",
        },
        docs_url="https://github.com/comfyanonymous/ComfyUI",
        tags=["comfyui", "workflow"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        base_url = settings.get("base_url")
        workflow_path = settings.get("workflow")
        if not base_url or not workflow_path:
            raise ProviderError("ComfyUI provider requires base_url and workflow.")
        workflow_file = Path(workflow_path).expanduser()
        if not workflow_file.exists():
            raise ProviderError(f"ComfyUI workflow not found: {workflow_file}")

        workflow_template = json.loads(workflow_file.read_text(encoding="utf-8"))
        prompt_placeholder = settings.get("prompt_input", "{{image_base64}}")
        timeout = float(settings.get("timeout", 180))
        panels = ctx.data.get("panels") or []
        if not panels:
            target = ctx.ocr_dir / "ocr_results.json"
            target.write_text("[]", encoding="utf-8")
            return StageResult(
                payload=[],
                artifacts=[target],
                notes=["No panels available for OCR; skipping ComfyUI workflow."],
            )
        results: List[Dict[str, Any]] = []
        artifacts: List[Path] = []
        client = ComfyUIClient(base=base_url)

        for page in panels:
            page_path = Path(page["page_path"])
            if not _is_image(page_path):
                ctx.log(f"Skipping OCR for non-image resource: {page_path.name}")
                continue
            image = Image.open(page_path) if Image else None
            for panel in page.get("panels", []):
                bbox = panel.get("bbox")
                cropped_path = ctx.ocr_dir / f"{panel['panel_id']}.png"
                if image:
                    crop = image.crop(tuple(bbox)) if bbox else image
                    crop.save(cropped_path)
                    image_bytes = cropped_path.read_bytes()
                else:
                    image_bytes = page_path.read_bytes()
                encoded = base64.b64encode(image_bytes).decode("utf-8")
                workflow_payload = _inject_base64(
                    workflow_template, prompt_placeholder, encoded
                )
                response = client.queue_prompt(workflow_payload)
                prompt_id = response.get("prompt_id")
                if not prompt_id:
                    raise ProviderError("ComfyUI did not return a prompt_id.")
                history = client.wait_for_history(prompt_id, timeout=timeout)
                text_output = _extract_comfyui_text(history)
                if text_output is None:
                    raise ProviderError(
                        "ComfyUI workflow did not produce a text output."
                    )
                results.append(
                    {
                        "panel_id": panel["panel_id"],
                        "page": page["page"],
                        "text": text_output.strip(),
                        "provider": self.metadata.id,
                        "confidence": 0.7 if text_output.strip() else 0.0,
                    }
                )
                artifacts.append(cropped_path)
        target = ctx.ocr_dir / "ocr_results.json"
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return StageResult(payload=results, artifacts=[target] + artifacts)


class AzureComputerVisionProvider(StageProvider):
    metadata = ProviderMetadata(
        id="azure_vision",
        stage="ocr",
        label="Azure Computer Vision",
        kind="paid",
        description="Azure Cognitive Services OCR endpoint.",
        default_settings={
            "endpoint": "https://<region>.api.cognitive.microsoft.com/vision/v3.2/ocr",
            "api_key": "",
            "language": "unk",
        },
        docs_url="https://learn.microsoft.com/azure/cognitive-services/computer-vision/overview-ocr",
        tags=["cloud", "rest"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        endpoint = settings.get("endpoint")
        api_key = settings.get("api_key")
        if not endpoint or not api_key:
            raise ProviderError("Azure OCR requires endpoint and api_key settings.")
        params = {
            "language": settings.get("language", "unk"),
            "detectOrientation": "true",
        }
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/octet-stream",
        }
        panels = ctx.data.get("panels") or []
        if not panels:
            target = ctx.ocr_dir / "ocr_results.json"
            target.write_text("[]", encoding="utf-8")
            return StageResult(
                payload=[],
                artifacts=[target],
                notes=["No panels available for OCR; skipping Azure Vision."],
            )
        results: List[Dict[str, Any]] = []
        for page in panels:
            page_path = Path(page["page_path"])
            if not _is_image(page_path):
                ctx.log(f"Skipping OCR for non-image resource: {page_path.name}")
                continue
            for panel in page.get("panels", []):
                crop_bytes = _extract_panel_bytes(page_path, panel.get("bbox"))
                response = requests.post(
                    endpoint,
                    params=params,
                    headers=headers,
                    data=crop_bytes,
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                lines = _collect_azure_lines(payload)
                text = " ".join(lines)
                results.append(
                    {
                        "panel_id": panel["panel_id"],
                        "page": page["page"],
                        "text": text.strip(),
                        "provider": self.metadata.id,
                        "confidence": 0.75 if text.strip() else 0.0,
                    }
                )
        target = ctx.ocr_dir / "ocr_results.json"
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return StageResult(payload=results, artifacts=[target])


class GoogleVisionProvider(StageProvider):
    metadata = ProviderMetadata(
        id="google_vision",
        stage="ocr",
        label="Google Cloud Vision",
        kind="paid",
        description="Google Cloud Vision OCR via REST API.",
        default_settings={
            "api_key": "",
            "language_hints": ["en"],
        },
        docs_url="https://cloud.google.com/vision/docs/ocr",
        tags=["cloud", "rest"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        api_key = settings.get("api_key")
        if not api_key:
            raise ProviderError("Google Vision OCR requires an api_key.")
        language_hints = settings.get("language_hints") or []
        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
        panels = ctx.data.get("panels") or []
        if not panels:
            target = ctx.ocr_dir / "ocr_results.json"
            target.write_text("[]", encoding="utf-8")
            return StageResult(
                payload=[],
                artifacts=[target],
                notes=["No panels available for OCR; skipping Google Vision."],
            )
        results: List[Dict[str, Any]] = []
        for page in panels:
            page_path = Path(page["page_path"])
            if not _is_image(page_path):
                ctx.log(f"Skipping OCR for non-image resource: {page_path.name}")
                continue
            for panel in page.get("panels", []):
                crop_bytes = _extract_panel_bytes(page_path, panel.get("bbox"))
                image_b64 = base64.b64encode(crop_bytes).decode("utf-8")
                request_payload = {
                    "requests": [
                        {
                            "image": {"content": image_b64},
                            "features": [{"type": "TEXT_DETECTION"}],
                            "imageContext": {"languageHints": language_hints},
                        }
                    ]
                }
                response = requests.post(url, json=request_payload, timeout=30)
                response.raise_for_status()
                annotations = response.json().get("responses", [{}])[0]
                text = annotations.get("fullTextAnnotation", {}).get("text", "")
                results.append(
                    {
                        "panel_id": panel["panel_id"],
                        "page": page["page"],
                        "text": text.strip(),
                        "provider": self.metadata.id,
                        "confidence": 0.78 if text.strip() else 0.0,
                    }
                )
        target = ctx.ocr_dir / "ocr_results.json"
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return StageResult(payload=results, artifacts=[target])


class PlaceholderGroupingProvider(StageProvider):
    metadata = ProviderMetadata(
        id="page_flow",
        stage="group",
        label="Page flow grouping",
        kind="open_source",
        description=(
            "Organize panels sequentially per page, producing one scene entry per page."
        ),
        tags=["deterministic"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        panels = ctx.data.get("panels") or []
        ocr_results = ctx.data.get("ocr") or []
        results: List[Dict[str, Any]] = []
        ocr_by_panel = {entry["panel_id"]: entry for entry in ocr_results}
        for index, page in enumerate(panels, start=1):
            scene_id = f"{ctx.job_id}_scene_{index:03d}"
            panel_entries: List[Dict[str, Any]] = []
            for panel in page.get("panels", []):
                ocr_entry = ocr_by_panel.get(panel["panel_id"], {})
                panel_entries.append(
                    {
                        "panel_id": panel["panel_id"],
                        "page": page["page"],
                        "text": ocr_entry.get("text") or "",
                        "confidence": ocr_entry.get("confidence", 0.0),
                        "bbox": panel.get("bbox"),
                        "normalized_bbox": panel.get("normalized_bbox"),
                    }
                )
            results.append(
                {
                    "scene_id": scene_id,
                    "page": page["page"],
                    "panels": panel_entries,
                }
            )
        target = ctx.group_dir / "groups.json"
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return StageResult(payload=results, artifacts=[target])


class PatternSpeakerProvider(StageProvider):
    metadata = ProviderMetadata(
        id="pattern_match",
        stage="speaker",
        label="Pattern-based speaker detection",
        kind="open_source",
        description=(
            "Detect speakers using colon-prefixed patterns and simple heuristics. "
            "Falls back to Narrator when no explicit speaker is present."
        ),
        tags=["deterministic"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        grouped = ctx.data.get("groups") or []
        scenes: List[Dict[str, Any]] = []
        artifacts: List[Path] = []
        for index, group in enumerate(grouped, start=1):
            scene_id = group["scene_id"]
            lines: List[Dict[str, Any]] = []
            speakers_seen: set[str] = set()
            for order, panel in enumerate(group.get("panels", []), start=1):
                speaker, text = _split_speaker(panel.get("text", ""))
                if speaker:
                    speakers_seen.add(speaker)
                lines.append(
                    {
                        "order": order,
                        "speaker": speaker or "Narrator",
                        "text": text or panel.get("text", ""),
                        "meta": {
                            "panel_id": panel["panel_id"],
                            "confidence": panel.get("confidence", 0.0),
                        },
                    }
                )
            payload = {
                "scene_id": scene_id,
                "title": f"Draft Scene {index:03d}",
                "lines": lines,
                "speakers_detected": sorted(speakers_seen),
                "meta": {
                    "job_id": ctx.job_id,
                    "source": "manga_pipeline",
                },
            }
            target = ctx.scenes_dir / f"{scene_id}.json"
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            scenes.append(payload)
            artifacts.append(target)
        return StageResult(payload=scenes, artifacts=artifacts)


class LLMSpeakerProvider(StageProvider):
    metadata = ProviderMetadata(
        id="openai_dialogue",
        stage="speaker",
        label="OpenAI Dialogue Attribution",
        kind="paid",
        description=(
            "Use OpenAI GPT models for dialogue attribution across panels. "
            "Requires an API key with multimodal access."
        ),
        default_settings={
            "api_key": "",
            "model": "gpt-4o-mini",
            "endpoint": "https://api.openai.com/v1/chat/completions",
        },
        docs_url="https://platform.openai.com/docs/",
        tags=["llm", "cloud"],
    )

    def run(self, ctx: StageContext, settings: Dict[str, Any]) -> StageResult:
        api_key = settings.get("api_key")
        if not api_key:
            raise ProviderError("OpenAI speaker attribution requires api_key.")
        model = settings.get("model", "gpt-4o-mini")
        endpoint = settings.get(
            "endpoint", "https://api.openai.com/v1/chat/completions"
        )
        grouped = ctx.data.get("groups") or []
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        scenes: List[Dict[str, Any]] = []
        artifacts: List[Path] = []
        for index, group in enumerate(grouped, start=1):
            prompt = _build_llm_prompt(group)
            payload = {"model": model, "messages": prompt, "temperature": 0.2}
            response = requests.post(
                endpoint, json=payload, headers=headers, timeout=45
            )
            response.raise_for_status()
            content = response.json()
            text_block = _extract_openai_text(content)
            lines = _deserialize_llm_lines(text_block, group)
            scene_payload = {
                "scene_id": group["scene_id"],
                "title": f"Draft Scene {index:03d}",
                "lines": lines,
                "meta": {
                    "job_id": ctx.job_id,
                    "source": "manga_pipeline",
                    "provider": self.metadata.id,
                    "model": model,
                },
            }
            target = ctx.scenes_dir / f"{group['scene_id']}.json"
            target.write_text(json.dumps(scene_payload, indent=2), encoding="utf-8")
            scenes.append(scene_payload)
            artifacts.append(target)
        return StageResult(payload=scenes, artifacts=artifacts)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, StageProvider] = {}

    def register(self, provider: StageProvider) -> None:
        provider_id = provider.metadata.id
        if provider_id in self._providers:
            raise ValueError(f"Duplicate provider id: {provider_id}")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> StageProvider:
        if provider_id not in self._providers:
            raise KeyError(f"Provider not found: {provider_id}")
        return self._providers[provider_id]

    def providers_for_stage(self, stage: StageKey) -> List[ProviderMetadata]:
        return [
            provider.metadata
            for provider in self._providers.values()
            if provider.metadata.stage == stage
        ]

    def as_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {
            "segment": [],
            "ocr": [],
            "group": [],
            "speaker": [],
        }
        for provider in self._providers.values():
            result[provider.metadata.stage].append(provider.metadata.to_dict())
        for stage in result:
            result[stage].sort(key=lambda item: item["label"])
        return result


REGISTRY = ProviderRegistry()


def _inject_base64(
    template: Dict[str, Any], placeholder: str, value: str
) -> Dict[str, Any]:
    payload = json.loads(json.dumps(template))
    serialized = json.dumps(payload)
    serialized = serialized.replace(placeholder, value)
    return json.loads(serialized)


def _extract_panel_bytes(page_path: Path, bbox: Optional[List[int]]) -> bytes:
    if Image is None or not _is_image(page_path):
        return page_path.read_bytes()
    image = Image.open(page_path)
    try:
        crop = image.crop(tuple(bbox)) if bbox else image
        buffer_path = page_path.parent / f"tmp_crop_{time.time_ns()}.png"
        crop.save(buffer_path)
        data = buffer_path.read_bytes()
        buffer_path.unlink(missing_ok=True)
        return data
    finally:
        image.close()


def _extract_comfyui_text(history: Dict[str, Any]) -> Optional[str]:
    for entry in history.values():
        outputs = entry.get("outputs") or {}
        for node_outputs in outputs.values():
            for item in node_outputs:
                if item.get("type") == "text":
                    return item.get("text")
    return None


def _collect_azure_lines(payload: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for region in payload.get("regions", []):
        for line in region.get("lines", []):
            words = [word.get("text", "") for word in line.get("words", [])]
            lines.append(" ".join(words))
    return lines


def _rows_to_segments(rows: List[int], height: int) -> List[tuple[int, int]]:
    if not rows:
        return []
    segments: List[tuple[int, int]] = []
    pivot = 0
    deduped = sorted(set(rows))
    for split in deduped:
        if split - pivot > 10:
            segments.append((pivot, split))
            pivot = split
    if height - pivot > 10:
        segments.append((pivot, height))
    return segments


def _probe_image_size(path: Path) -> tuple[int, int]:
    if Image is None:
        return (1024, 1024)
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (1024, 1024)


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def _split_speaker(text: str) -> tuple[Optional[str], str]:
    if not text:
        return None, ""
    parts = text.split(":", 1)
    if len(parts) == 2 and parts[0].strip() and len(parts[0]) < 40:
        speaker = parts[0].strip()
        remainder = parts[1].strip()
        return speaker, remainder
    return None, text.strip()


def _build_llm_prompt(group: Dict[str, Any]) -> List[Dict[str, str]]:
    content_lines = "\n".join(
        f"Panel {idx+1}: {panel.get('text','')}"
        for idx, panel in enumerate(group.get("panels", []))
    )
    system_prompt = (
        "You are an assistant that rewrites manga panel text into structured dialogue "
        "entries with speaker labels. Output JSON lines with keys speaker and text."
    )
    user_prompt = (
        f"Panels for scene {group.get('scene_id')}:\n{content_lines}\n\n"
        "Return JSON array describing speaker and text for each line."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_openai_text(response: Dict[str, Any]) -> str:
    choices = response.get("choices") or []
    for choice in choices:
        message = choice.get("message") or {}
        content = message.get("content")
        if content:
            return content
    return ""


def _deserialize_llm_lines(raw: str, group: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [
                {
                    "order": idx + 1,
                    "speaker": entry.get("speaker", "Narrator"),
                    "text": entry.get("text", ""),
                    "meta": (
                        {"source_panel": group.get("panels", [])[idx]["panel_id"]}
                        if idx < len(group.get("panels", []))
                        else {}
                    ),
                }
                for idx, entry in enumerate(data)
            ]
    except Exception:  # pragma: no cover - fallback
        pass
    fallback: List[Dict[str, Any]] = []
    for idx, panel in enumerate(group.get("panels", []), start=1):
        fallback.append(
            {
                "order": idx,
                "speaker": "Narrator",
                "text": panel.get("text", ""),
                "meta": {"source_panel": panel.get("panel_id")},
            }
        )
    return fallback


def all_providers() -> Dict[str, List[Dict[str, Any]]]:
    return REGISTRY.as_dict()


def providers_for(stage: StageKey) -> List[ProviderMetadata]:
    return REGISTRY.providers_for_stage(stage)


def get_provider(provider_id: str) -> StageProvider:
    return REGISTRY.get(provider_id)


def default_provider_map() -> Dict[StageKey, str]:
    mapping: Dict[StageKey, str] = {
        "segment": "whitespace_split" if Image is not None else "basic_panel",
        "ocr": "pytesseract",
        "group": "page_flow",
        "speaker": "pattern_match",
    }
    if pytesseract is None:
        mapping["ocr"] = "easyocr" if easyocr is not None else "comfyui_i2t"
    return mapping


def register_defaults() -> None:
    REGISTRY.register(BasicSegmenter())
    REGISTRY.register(WhitespaceSegmenter())
    REGISTRY.register(TesseractOCRProvider())
    REGISTRY.register(EasyOCROCRProvider())
    REGISTRY.register(ComfyUIOCRProvider())
    REGISTRY.register(AzureComputerVisionProvider())
    REGISTRY.register(GoogleVisionProvider())
    REGISTRY.register(PlaceholderGroupingProvider())
    REGISTRY.register(PatternSpeakerProvider())
    REGISTRY.register(LLMSpeakerProvider())


register_defaults()

__all__ = [
    "StageContext",
    "StageResult",
    "ProviderMetadata",
    "ProviderRegistry",
    "ProviderError",
    "StageKey",
    "all_providers",
    "providers_for",
    "get_provider",
    "default_provider_map",
    "ProviderError",
]
