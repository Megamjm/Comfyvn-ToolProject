"""Production manga processing pipeline with provider integrations."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional

from comfyvn.manga.providers import (
    ProviderError,
    StageContext,
    StageKey,
    all_providers,
    default_provider_map,
    get_provider,
)

LOGGER = logging.getLogger(__name__)
JobState = Literal["queued", "running", "done", "error"]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

try:  # pragma: no cover - optional dependency
    from comfyvn.core.job_lifecycle import JobLifecycle  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    JobLifecycle = None  # type: ignore

_LIFECYCLE = JobLifecycle() if JobLifecycle else None


@dataclass(slots=True)
class PipelineConfig:
    """Configuration selected for a pipeline job."""

    sources: List[Path]
    providers: Dict[StageKey, str]
    provider_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MangaJob:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: JobState = "queued"
    progress: float = 0.0
    message: str = "Queued"
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    providers: Dict[StageKey, str] = field(default_factory=dict)
    provider_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    stages: Dict[StageKey, Dict[str, Any]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def to_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            payload = {
                "job": self.id,
                "state": self.state,
                "progress": round(self.progress, 3),
                "message": self.message,
                "error": self.error,
                "created_at": self.created_at.isoformat(),
                "artifacts": self.artifacts,
                "providers": self.providers,
                "provider_settings": self.provider_settings,
                "metadata": self.metadata,
                "stages": self.stages,
                "notes": self.notes[:],
                "events": self.events[-20:],
            }
            if self.started_at:
                payload["started_at"] = self.started_at.isoformat()
            if self.finished_at:
                payload["finished_at"] = self.finished_at.isoformat()
            return payload

    def record_event(self, stage: str, message: str) -> None:
        with self.lock:
            event = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "message": message,
            }
            self.events.append(event)
            LOGGER.debug("Job %s %s -> %s", self.id, stage, message)

    def set_state(self, state: JobState, message: Optional[str] = None) -> None:
        with self.lock:
            self.state = state
            if message:
                self.message = message
            if state == "running" and self.started_at is None:
                self.started_at = datetime.now(timezone.utc)
            if state in {"done", "error"}:
                self.finished_at = datetime.now(timezone.utc)

    def update_progress(self, value: float, message: Optional[str] = None) -> None:
        with self.lock:
            self.progress = value
            if message:
                self.message = message


class MangaPipeline:
    """Coordinate manga processing jobs."""

    def __init__(self, base_root: Path = Path("data/manga")) -> None:
        self.base_root = base_root.expanduser().resolve()
        self.base_root.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, MangaJob] = {}
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------
    def start(self, config: PipelineConfig, root: Optional[Path] = None) -> str:
        job = MangaJob()
        job.providers = dict(config.providers)
        job.provider_settings = dict(config.provider_settings)
        job.metadata = dict(config.metadata)
        root_path = (root or self.base_root).expanduser().resolve()
        root_path.mkdir(parents=True, exist_ok=True)

        job_root = root_path / job.id
        artifact_paths = {
            "base": job_root,
            "raw": job_root / "raw",
            "ocr": job_root / "ocr",
            "group": job_root / "group",
            "scenes": job_root / "scenes",
            "logs": job_root / "logs",
        }
        for path in artifact_paths.values():
            path.mkdir(parents=True, exist_ok=True)
        job.artifacts = {key: str(path) for key, path in artifact_paths.items()}

        with self._lock:
            self._jobs[job.id] = job

        self._persist_manifest(job, {"state": "queued"})
        if _LIFECYCLE:
            _LIFECYCLE.add(
                job.id,
                {
                    "kind": "manga_pipeline",
                    "providers": job.providers,
                    "state": "queued",
                    "artifact_root": str(job_root),
                },
            )

        future = self._executor.submit(
            self._run_job, job, config, artifact_paths, config.sources
        )
        future.add_done_callback(lambda _: None)
        return job.id

    def status(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return {"job": job_id, "state": "not_found"}
        return job.to_snapshot()

    def list_jobs(self) -> List[str]:
        with self._lock:
            return sorted(self._jobs.keys())

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------
    def _run_job(
        self,
        job: MangaJob,
        config: PipelineConfig,
        paths: Dict[str, Path],
        sources: Iterable[Path],
    ) -> None:
        job.set_state("running", "Preparing job")
        job.record_event("pipeline", "Job started")
        self._persist_manifest(job, {"state": "running"})
        try:
            raw_pages = self._ingest_sources(job, paths["raw"], sources)
            stage_data: Dict[str, Any] = {"pages": [str(path) for path in raw_pages]}
            stages: List[StageKey] = ["segment", "ocr", "group", "speaker"]
            for index, stage in enumerate(stages, start=1):
                provider_id = (
                    config.providers.get(stage) or default_provider_map()[stage]
                )
                settings = config.provider_settings.get(stage, {})
                job.record_event(stage, f"Starting stage with provider {provider_id}")
                result = self._run_stage(
                    job=job,
                    stage=stage,
                    provider_id=provider_id,
                    settings=settings,
                    paths=paths,
                    raw_pages=raw_pages,
                    stage_data=stage_data,
                )
                stage_data[stage] = result.payload
                job.stages[stage] = {
                    "provider": provider_id,
                    "artifacts": [str(path) for path in result.artifacts],
                    "notes": result.notes,
                }
                job.notes.extend(result.notes)
                progress = index / len(stages)
                job.update_progress(progress, f"{stage} complete")
                job.record_event(stage, "Stage complete")
            manifest = {
                "state": "done",
                "providers": job.providers,
                "metadata": job.metadata,
                "artifacts": job.artifacts,
                "stages": job.stages,
            }
            self._persist_manifest(job, manifest)
            job.set_state("done", "Pipeline complete")
            job.update_progress(1.0, "Pipeline complete")
            job.record_event("pipeline", "Job finished")
            if _LIFECYCLE:
                _LIFECYCLE.mark_done(job.id, manifest)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Manga pipeline job %s failed: %s", job.id, exc)
            job.error = str(exc)
            job.set_state("error", "Pipeline failed")
            job.record_event("pipeline", f"Error: {exc}")
            self._persist_manifest(job, {"state": "error", "error": str(exc)})

    def _run_stage(
        self,
        *,
        job: MangaJob,
        stage: StageKey,
        provider_id: str,
        settings: Dict[str, Any],
        paths: Dict[str, Path],
        raw_pages: List[Path],
        stage_data: Dict[str, Any],
    ):
        provider = get_provider(provider_id)
        ctx = StageContext(
            job_id=job.id,
            stage=stage,
            base_dir=Path(job.artifacts["base"]),
            raw_dir=paths["raw"],
            ocr_dir=paths["ocr"],
            group_dir=paths["group"],
            scenes_dir=paths["scenes"],
            pages=raw_pages,
            data={
                "panels": stage_data.get("segment"),
                "ocr": stage_data.get("ocr"),
                "groups": stage_data.get("group"),
            },
            log=lambda msg: job.record_event(stage, msg),
            metadata=job.metadata,
        )
        try:
            result = provider.run(ctx, settings)
        except ProviderError as exc:
            job.record_event(stage, f"Provider error: {exc}")
            raise
        return result

    def _ingest_sources(
        self, job: MangaJob, raw_dir: Path, sources: Iterable[Path]
    ) -> List[Path]:
        ingested: List[Path] = []
        for source in sources:
            if not source.exists():
                job.record_event("ingest", f"Skipping missing source {source}")
                continue
            target = raw_dir / source.name
            if source.is_file():
                if source.suffix.lower() not in IMAGE_EXTS:
                    job.record_event(
                        "ingest", f"Skipping unsupported file {source.name}"
                    )
                    continue
                shutil.copy2(source, target)
                ingested.append(target)
            elif source.is_dir():
                for path in sorted(source.rglob("*")):
                    if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                        rel = path.relative_to(source)
                        target_path = raw_dir / rel.name
                        shutil.copy2(path, target_path)
                        ingested.append(target_path)
                    elif path.is_file():
                        job.record_event(
                            "ingest", f"Skipping unsupported file {path.name}"
                        )
        if not ingested:
            placeholder = raw_dir / "placeholder.txt"
            placeholder.write_text(
                "No input assets supplied. Provide images when starting the pipeline.",
                encoding="utf-8",
            )
            ingested.append(placeholder)
        job.record_event("ingest", f"Ingested {len(ingested)} source files.")
        return ingested

    def _persist_manifest(self, job: MangaJob, payload: Dict[str, Any]) -> None:
        base = Path(job.artifacts["base"])
        manifest_path = base / "manifest.json"
        snapshot = {"job": job.id, "updated_at": datetime.now(timezone.utc).isoformat()}
        snapshot.update(payload)
        manifest_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


PIPELINE = MangaPipeline()


def start(root: Path, config: PipelineConfig) -> str:
    """Start a new manga pipeline job."""
    return PIPELINE.start(config, root=root)


def status(job_id: str) -> Dict[str, Any]:
    """Retrieve job status."""
    return PIPELINE.status(job_id)


def list_jobs() -> List[str]:
    return PIPELINE.list_jobs()


def provider_catalog() -> Dict[str, List[Dict[str, Any]]]:
    return all_providers()


def build_config(
    *,
    sources: Iterable[str],
    providers: Optional[Dict[str, str]] = None,
    provider_settings: Optional[Dict[str, Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> PipelineConfig:
    resolved_sources = [Path(src).expanduser().resolve() for src in sources]
    default_map = default_provider_map()
    resolved_providers: Dict[StageKey, str] = default_map.copy()
    if providers:
        for key, value in providers.items():
            stage = key.lower()
            if stage in resolved_providers and value:
                resolved_providers[stage] = value
    resolved_settings: Dict[str, Dict[str, Any]] = {}
    if provider_settings:
        for key, value in provider_settings.items():
            resolved_settings[key.lower()] = dict(value)
    return PipelineConfig(
        sources=resolved_sources,
        providers=resolved_providers,
        provider_settings=resolved_settings,
        metadata=dict(metadata or {}),
    )


__all__ = [
    "PIPELINE",
    "PipelineConfig",
    "MangaPipeline",
    "MangaJob",
    "start",
    "status",
    "list_jobs",
    "build_config",
    "provider_catalog",
]
