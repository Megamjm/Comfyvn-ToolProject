# comfyvn/modules/orchestration/pipeline_manager.py
# ⚙️ 3. Server Core Production Chat — Pipeline Orchestrator (v2.6)
# Coordinates LM Studio → Preprocess → ComfyUI render → Ren'Py export
# Compatible with Server Core v2.5+ (jobs, WS/SSE events)
# [ComfyVN Architect | Chat: Server Core Production]

from __future__ import annotations
import os
import time
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

# ---- Internal dependencies (respecting refactored folder layout) ----
from comfyvn.core.mode_manager import ModeManager
from comfyvn.core.event_bus import EventBus
from comfyvn.core.job_manager import JobManager
from comfyvn.core.scene_preprocessor import preprocess_scene
from comfyvn.modules.orchestration.lmstudio_bridge import LMBridge
from comfyvn.core.workflow_bridge import ComfyUIBridge
from comfyvn.integrations.renpy_bridge import RenPyBridge


# -----------------------------
# Configuration dataclasses
# -----------------------------
@dataclass
class PipelineOptions:
    """Toggles and parameters for the pipeline."""

    use_lm: bool = True  # run LM generation/expansion
    do_render: bool = True  # send prompt to ComfyUI
    do_export_renpy: bool = True  # export .rpy
    wait_render: bool = True  # wait for render completion (poll)
    render_timeout: int = 60  # seconds
    render_interval: float = 2.0  # polling interval
    output_file: str = (
        "latest.png"  # ComfyUI output file name (saved under its configured dir)
    )
    export_dir: str = (
        "./exports/renpy"  # Ren'Py export dir (RenPyBridge should also ensure)
    )
    archive_dir: str = "./data/scenes"  # where to save scene snapshots (JSON)
    lm_model: str = "gpt-4-turbo"  # OpenAI-compatible model name
    lm_max_tokens: int = 700  # generation budget
    # Reserved for future
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Runtime singletons and state references."""

    mode_manager: ModeManager
    job_manager: JobManager
    event_bus: EventBus
    lm_bridge: LMBridge
    comfy_bridge: ComfyUIBridge
    renpy_bridge: RenPyBridge


# -----------------------------
# Orchestrator
# -----------------------------
class PipelineManager:
    """
    High-level orchestrator for a single or multiple scene tasks.
    - Emits granular progress via JobManager (which broadcasts over EventBus).
    - Archives input/outputs to enable reproducibility and recovery.
    """

    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx
        os.makedirs("./exports/renpy", exist_ok=True)
        os.makedirs("./data/scenes", exist_ok=True)

    # ---------- Utilities ----------
    def _emit(
        self,
        job_id: str,
        status: str,
        progress: float,
        meta: Optional[Dict[str, Any]] = None,
    ):
        """Convenience wrapper to update JobManager and keep progress consistent."""
        payload: Dict[str, Any] = {
            "status": status,
            "progress": max(0.0, min(1.0, float(progress))),
        }
        if meta:
            payload.update(meta)
        self.ctx.job_manager.update(job_id, **payload)

    def _archive_json(self, data: Dict[str, Any], base_name: str, out_dir: str) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe = base_name.replace(" ", "_").replace("/", "_")
        path = os.path.join(out_dir, f"{safe}_{ts}.json")
        os.makedirs(out_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    # ---------- Core steps ----------
    def _lm_generate(
        self, scene_input: Dict[str, Any], options: PipelineOptions
    ) -> Dict[str, Any]:
        """
        Expand or refine scene text via LM; expected OpenAI chat format.
        Returns a dict with at least {'text': str}, may include extra keys.
        """
        messages = [
            {
                "role": "system",
                "content": "You are a visual novel scene writer. Expand and polish dialogue succinctly.",
            },
            {"role": "user", "content": json.dumps(scene_input, ensure_ascii=False)},
        ]
        res = self.ctx.lm_bridge.chat(
            messages, model=options.lm_model, max_tokens=options.lm_max_tokens
        )
        if res and not res.get("error"):
            try:
                content = res["choices"][0]["message"]["content"]
            except Exception:
                # fallback if unexpected shape
                content = json.dumps(res, ensure_ascii=False)
            return {"text": content, "lm_raw": res}
        # graceful degrade: return original text if LM fails
        return {
            "text": scene_input.get("text", ""),
            "lm_error": res.get("error", "unknown_error") if res else "no_response",
        }

    def _render(
        self,
        prompt_text: str,
        options: PipelineOptions,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """Queue render and optionally wait for completion."""

        # Offer mid-progress callbacks to JobManager
        def _cb(p, stage):
            if progress_cb:
                progress_cb(p, stage)

        # If ComfyUIBridge supports progress callback:
        try:
            result = self.ctx.comfy_bridge.queue_and_wait(
                prompt_text,
                output_file=options.output_file,
                wait=options.wait_render,
                progress_cb=_cb,
            )
        except TypeError:
            # Older comfy_bridge without progress_cb param:
            result = self.ctx.comfy_bridge.queue_and_wait(
                prompt_text, output_file=options.output_file, wait=options.wait_render
            )

        # If waiting synchronously wasn't supported by bridge, we can poll here as a fallback:
        if (
            options.wait_render
            and isinstance(result, dict)
            and result.get("status") == "polling"
        ):
            job_id = result.get("job_id")
            start = time.time()
            while time.time() - start < options.render_timeout:
                hist = self.ctx.comfy_bridge.poll_job(
                    job_id,
                    timeout=int(options.render_interval),
                    interval=options.render_interval,
                )
                if hist.get("status") == "complete":
                    return hist
                if progress_cb:
                    progress_cb(
                        0.6
                        + 0.3
                        * ((time.time() - start) / max(1, options.render_timeout)),
                        "waiting",
                    )
            return {"status": "timeout", "job_id": job_id}

        return result

    def _export_renpy(self, scene_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Save a single-scene Ren'Py file; returns {file, scene_id, script_text}."""
        return self.ctx.renpy_bridge.save_script(scene_plan)

    # ---------- Public API ----------
    def run_scene_pipeline(
        self,
        job_id: str,
        scene_input: Dict[str, Any],
        options: Optional[PipelineOptions] = None,
    ) -> Dict[str, Any]:
        """
        One-shot pipeline:
            (optional) LM → Preprocess → (optional) Render → (optional) Export Ren'Py
        Emits progress updates to JobManager.
        Returns a payload summarizing outputs.
        """
        opts = options or PipelineOptions()
        mode = self.ctx.mode_manager.get_mode()

        # 1) Archive raw input
        self._emit(job_id, "queued", 0.05, {"stage": "archive_input"})
        input_path = self._archive_json(
            scene_input, scene_input.get("scene_id", "scene_input"), opts.archive_dir
        )

        # 2) LM expand (optional)
        if opts.use_lm:
            self._emit(job_id, "processing:lm_generate", 0.15, {"stage": "lm"})
            lm_out = self._lm_generate(scene_input, opts)
            # Merge/override the text field minimally; preserve original structure
            scene_input = {
                **scene_input,
                **({"text": lm_out.get("text", scene_input.get("text", ""))}),
            }
            lm_meta_path = self._archive_json(
                lm_out,
                scene_input.get("scene_id", "scene_input") + "_lm",
                opts.archive_dir,
            )
        else:
            lm_out, lm_meta_path = None, None

        # 3) Preprocess → plan
        self._emit(job_id, "processing:preprocess", 0.3, {"stage": "preprocess"})
        plan = preprocess_scene(scene_input, mode)
        plan_path = self._archive_json(
            plan, plan.get("scene_id", "scene_plan"), opts.archive_dir
        )

        # 4) Render via ComfyUI (optional)
        render_result = None
        if opts.do_render:
            self._emit(job_id, "processing:render_dispatch", 0.45, {"stage": "render"})

            def progress_cb(pct: float, stage: str):
                # map 0..1 into 0.45..0.85
                mapped = 0.45 + 0.4 * float(pct)
                self._emit(
                    job_id, f"processing:render_{stage}", mapped, {"stage": "render"}
                )

            render_result = self._render(
                plan["render_ready_prompt"], opts, progress_cb=progress_cb
            )
            self._emit(
                job_id,
                "processing:render_done",
                0.88,
                {
                    "stage": "render",
                    "render_status": (
                        render_result.get("status")
                        if isinstance(render_result, dict)
                        else "unknown"
                    ),
                },
            )

        # 5) Export Ren'Py (optional)
        renpy_result = None
        if opts.do_export_renpy:
            self._emit(job_id, "processing:renpy_export", 0.92, {"stage": "renpy"})
            renpy_result = self._export_renpy(plan)
            self._emit(job_id, "processing:renpy_done", 0.96, {"stage": "renpy"})

        # 6) Finalize
        out = {
            "input_archive": input_path,
            "lm_meta_archive": lm_meta_path,
            "plan_archive": plan_path,
            "render_result": render_result,
            "renpy_export": renpy_result,
            "mode": mode,
        }
        self._emit(
            job_id,
            "complete",
            1.0,
            {
                "stage": "done",
                "result": {
                    "has_render": bool(render_result),
                    "has_script": bool(renpy_result),
                },
            },
        )
        self.ctx.job_manager.complete(job_id, out)
        return out

    def run_chapter_pipeline(
        self,
        job_id: str,
        scenes: List[Dict[str, Any]],
        options: Optional[PipelineOptions] = None,
        chapter_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Multi-scene pipeline: processes a list of scenes and compiles a Ren'Py chapter.
        Renders each scene (optional) and exports a combined .rpy.
        """
        opts = options or PipelineOptions()
        mode = self.ctx.mode_manager.get_mode()
        chapter = chapter_name or f"chapter_{time.strftime('%Y%m%d_%H%M%S')}"

        chapter_archives: List[str] = []
        render_results: Dict[str, Any] = {}
        processed_scenes: List[Dict[str, Any]] = []

        total = max(1, len(scenes))
        for idx, raw_scene in enumerate(scenes, start=1):
            step_base = 0.05 + 0.9 * ((idx - 1) / total)
            self._emit(
                job_id,
                f"processing:scene_{idx}/{total}",
                step_base,
                {"stage": "scene", "scene_index": idx},
            )

            # LM (optional)
            use = raw_scene.copy()
            if opts.use_lm:
                lm_out = self._lm_generate(use, opts)
                use["text"] = lm_out.get("text", use.get("text", ""))

            # Preprocess
            plan = preprocess_scene(use, mode)
            processed_scenes.append(plan)
            arc = self._archive_json(
                plan, plan.get("scene_id", f"scene_{idx}"), opts.archive_dir
            )
            chapter_archives.append(arc)

            # Render (optional)
            if opts.do_render:

                def cb(pct: float, stage: str):
                    mapped = step_base + 0.6 * (pct / total)
                    self._emit(
                        job_id,
                        f"processing:scene_{idx}_render_{stage}",
                        min(mapped, 0.98),
                        {"stage": "render", "scene_index": idx},
                    )

                render_results[plan.get("scene_id", f"scene_{idx}")] = self._render(
                    plan["render_ready_prompt"], opts, progress_cb=cb
                )

        # Compile Ren'Py chapter
        renpy_chapter = None
        if opts.do_export_renpy:
            self._emit(job_id, "processing:compile_chapter", 0.98, {"stage": "renpy"})
            # Reuse RenPyBridge.compile_scenes if present; fallback to multiple save_script
            compile_fn = getattr(self.ctx.renpy_bridge, "compile_scenes", None)
            if callable(compile_fn):
                renpy_chapter = compile_fn(
                    processed_scenes, chapter_name=chapter, make_entry_label=True
                )
            else:
                # fallback: export each separately, provide a manifest
                manifest = []
                for sc in processed_scenes:
                    res = self.ctx.renpy_bridge.save_script(sc)
                    manifest.append(res)
                renpy_chapter = {
                    "file": None,
                    "chapter_label": chapter,
                    "manifest": manifest,
                    "script_text": None,
                }

        out = {
            "chapter_name": chapter,
            "archives": chapter_archives,
            "render_results": render_results if opts.do_render else None,
            "renpy_export": renpy_chapter,
            "mode": mode,
        }
        self._emit(
            job_id,
            "complete",
            1.0,
            {"stage": "done", "result": {"scenes": len(scenes)}},
        )
        self.ctx.job_manager.complete(job_id, out)
        return out
