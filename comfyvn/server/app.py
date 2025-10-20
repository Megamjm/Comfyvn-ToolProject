from PySide6.QtGui import QAction
from comfyvn.server.modules.import_vn_v07_api import router as ImportV07Router
from comfyvn.server.modules.render_v07_api import router as RenderV07Router
from comfyvn.core.event_hub_v05 import EventHub
from comfyvn.server.modules.settings_v06_api import router as SettingsV06Router
from comfyvn.server.modules.jobs_v05_api import router as JobsV05Router
from comfyvn.server.modules.events_v05_api import router as EventsV05Router
from comfyvn.server.modules.db_v05_api import router as DBv05Router
from comfyvn.server.modules.scene_director_api import router as DirectorRouter
from comfyvn.server.modules.comfyui_bridge_api import router as ComfyUIBridgeRouter
from comfyvn.server.modules.assets_pipeline_api import router as AssetsPipelineRouter
from comfyvn.server.modules.device_api import router as DeviceRouter
from comfyvn.server.modules.export_scene_api import router as ExportSceneRouter
from comfyvn.server.modules.playground_compose_api import router as PlaygroundComposeRouter
from comfyvn.server.modules.render_bridge_api import router as RenderBridgeRouter
from comfyvn.server.modules.scene_api import router as SceneRouter
from comfyvn.server.modules.voice_api import router as VoiceRouter
from comfyvn.server.modules.persona_api import router as PersonaRouter
from comfyvn.server.modules.lore_api import router as LoreRouter
from comfyvn.server.modules.comfy_bridge_api import router as ComfyBridgeRouter

# comfyvn/app.py
# ⚙️ ComfyVN Server Core — Unified Backend Bootstrap (v3.5.4)
# [Patch Updates Channel | Synced with core/security.py + render_manager.py + smokecheck phase79]

import os, threading
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# -------------------------------------------------------
# Core System Imports
# -------------------------------------------------------
from comfyvn.server.core.errors import register_exception_handlers
from comfyvn.server.core.limits import BodyLimitMiddleware, TimeoutMiddleware
from comfyvn.server.core.logging_ex import setup_logging
from comfyvn.server.core.event_bus import EventBus
from comfyvn.server.core.job_manager import JobManager
from comfyvn.server.core.render_manager import RenderManager
from comfyvn.server.core.middleware_ex import RequestIDMiddleware, TimingMiddleware
from comfyvn.server.core.security import SecurityHeadersMiddleware
from comfyvn.ext.plugins import PluginManager

from comfyvn.core.state_manager import StateManager
from comfyvn.core.system_registry import SystemRegistry
from comfyvn.core.plugin_loader import PluginLoader

# -------------------------------------------------------
# Routers — Core and Compatibility
# -------------------------------------------------------
from comfyvn.server.modules.scanner_api import router as ScannerRouter
from comfyvn.server.modules.system_api import router as SystemRouter
from comfyvn.server.modules.v1_system_api import router as V1SystemRouter
from comfyvn.server.modules.secure_api import router as SecureRouter
from comfyvn.server.modules.jobs_health_api import router as JobsHealthRouter
from comfyvn.server.modules.jobs_test_api import router as JobsTestRouter
from comfyvn.server.modules.metrics_api import router as MetricsRouter
from comfyvn.server.modules.home_api import router as HomeRouter
from comfyvn.server.modules.jobs_api import get_router as JobsRouterFactory
from comfyvn.server.modules.scene_analyzer_api import router as SceneAnalyzerRouter
from comfyvn.server.modules.godot_proxy_api import router as GodotProxyRouter
from comfyvn.server.modules.tts_api import router as TTSRouter
from comfyvn.server.modules.music_mood_api import router as MusicMoodRouter
from comfyvn.server.modules.i18n_api import router as I18nRouter
from comfyvn.server.modules.replay_api import router as ReplayRouter
from comfyvn.server.modules.branchmap_api import router as BranchMapRouter
from comfyvn.server.modules.continuity_api import router as ContinuityRouter
from comfyvn.server.modules.market_api import router as MarketRouter

# -------------------------------------------------------

from comfyvn.server.modules.devices_api import router as DevicesRouter

from comfyvn.server.modules.plugin_api  import router as PluginAdminRouter

from comfyvn.server.modules.gui_api     import router as GuiRouter

from comfyvn.server.modules.settings_api import router as SettingsRouter
# Optional / Extended Modules
# -------------------------------------------------------
from comfyvn.server.modules.control_api import router as ControlRouter
from comfyvn.server.modules.npc_api import router as NpcRouter
from comfyvn.server.modules.translation_api import router as TranslationRouter
from comfyvn.server.modules.playground_api import router as PlaygroundRouter
from comfyvn.server.modules.assets_api_ex import router as AssetsXRouter
from comfyvn.server.modules.workflows_api import router as WorkflowsRouter, set_job_manager as _set_wf_jm
from comfyvn.server.modules.scheduler_api import SchedulerRouter
from comfyvn.server.modules.asset_store_api import router as AssetStoreRouter
from comfyvn.server.modules.webhooks_api import router as WebhooksRouter
from comfyvn.server.modules.events_api import router as EventsRouter
from comfyvn.server.modules.bridge_api import router as BridgeRouter
from comfyvn.server.modules.roleplay_api import router as RoleplayRouter
from comfyvn.server.modules.mass_edit_api import router as MassEditRouter
from comfyvn.server.modules.env_api import router as EnvRouter
from comfyvn.server.modules.admin_api import router as AdminRouter
from comfyvn.server.modules.meta_backcompat_api import router as MetaCompatRouter
from comfyvn.server.modules.jobs_backcompat_api import router as JobsCompatRouter
from comfyvn.server.modules.export_bundle_api import router as ExportBundleRouter
from comfyvn.server.modules.packager_api import router as PackagerRouter
from comfyvn.server.modules.telemetry_api import router as TelemetryRouter
from comfyvn.server.modules.agent_api import router as AgentRouter
from comfyvn.server.modules.bridgehub_api import router as BridgeHubRouter
from comfyvn.server.modules.sessions_api import router as SessionsRouter
from comfyvn.server.modules.orchestrator_api import router as OrchestratorRouter
from comfyvn.core.orchestrator import Orchestrator
from comfyvn.server.modules.diagnostics_api import router as DiagnosticsRouter
from comfyvn.server.modules.log_control_api import router as LogControlRouter
from comfyvn.server.modules.health_api import router as HealthRouter
from comfyvn.server.modules.render_api import router as RenderRouter, set_render_manager as _set_rm
from comfyvn.server.modules.events_ws_api import router as EventsRealtimeRouter
from comfyvn.server.modules.events_bus_api import router as EventsBusRouter
from comfyvn.server.modules.job_orchestrator_api import router as JobOrchestratorRouter
from comfyvn.server.modules.render_feedback_api import router as RenderFeedbackRouter
from comfyvn.server.modules.scene_persistence_api import router as SceneIORouter
from comfyvn.server.modules.replay_memory_api import router as ReplayMemRouter



# -------------------------------------------------------
# Logging Setup
# -------------------------------------------------------
setup_logging()

try:
    from fastapi.responses import ORJSONResponse as _ORJSON
    _DEFAULT = _ORJSON
except Exception:
    _DEFAULT = None

app = FastAPI(title="ComfyVN", version="0.8.0",
app.include_router(r_flow_registry_router)  # [Main window update chat]
app.include_router(r_health_router)  # [Main window update chat]
app.include_router(r_ops_routes_router)  # [Main window update chat]
app.include_router(jobs_jobs_api_router)  # [Main window update chat]
app.include_router(root_jobs_api_router)  # [Main window update chat]
app.include_router(router_snapshots_api_router)  # [Main window update chat]
app.include_router(router_admin_api_router)  # [Main window update chat]
app.include_router(router_agent_api_router)  # [Main window update chat]
app.include_router(router_artifacts_api_router)  # [Main window update chat]
app.include_router(router_assets_api_router)  # [Main window update chat]
app.include_router(router_assets_api_ex_router)  # [Main window update chat]
app.include_router(router_assets_pipeline_api_router)  # [Main window update chat]
app.include_router(router_asset_store_api_router)  # [Main window update chat]
app.include_router(router_audit_api_router)  # [Main window update chat]
app.include_router(router_auth_api_router)  # [Main window update chat]
app.include_router(router_auth_oidc_api_router)  # [Main window update chat]
app.include_router(router_branchmap_api_router)  # [Main window update chat]
app.include_router(router_bridgehub_api_router)  # [Main window update chat]
app.include_router(router_bridge_api_router)  # [Main window update chat]
app.include_router(router_characters_api_router)  # [Main window update chat]
app.include_router(router_collab_api_router)  # [Main window update chat]
app.include_router(router_comfyui_bridge_api_router)  # [Main window update chat]
app.include_router(router_comfy_bridge_api_router)  # [Main window update chat]
app.include_router(router_continuity_api_router)  # [Main window update chat]
app.include_router(router_control_api_router)  # [Main window update chat]
app.include_router(router_db_api_router)  # [Main window update chat]
app.include_router(router_devices_api_router)  # [Main window update chat]
app.include_router(router_device_api_router)  # [Main window update chat]
app.include_router(router_diagnostics_api_router)  # [Main window update chat]
app.include_router(router_env_api_router)  # [Main window update chat]
app.include_router(router_events_api_router)  # [Main window update chat]
app.include_router(router_events_bus_api_router)  # [Main window update chat]
app.include_router(router_events_ws_api_router)  # [Main window update chat]
app.include_router(router_export_bundle_api_router)  # [Main window update chat]
app.include_router(router_export_hook_router)  # [Main window update chat]
app.include_router(router_export_scene_api_router)  # [Main window update chat]
app.include_router(router_godot_proxy_api_router)  # [Main window update chat]
app.include_router(router_gui_api_router)  # [Main window update chat]
app.include_router(router_health_api_router)  # [Main window update chat]
app.include_router(router_home_api_router)  # [Main window update chat]
app.include_router(router_i18n_api_router)  # [Main window update chat]
app.include_router(router_importers_api_router)  # [Main window update chat]
app.include_router(router_import_api_router)  # [Main window update chat]
app.include_router(router_import_vn_v07_api_router)  # [Main window update chat]
app.include_router(router_jobs_api_router)  # [Main window update chat]
app.include_router(router_jobs_backcompat_api_router)  # [Main window update chat]
app.include_router(router_jobs_health_api_router)  # [Main window update chat]
app.include_router(router_jobs_test_api_router)  # [Main window update chat]
app.include_router(router_job_orchestrator_api_router)  # [Main window update chat]
app.include_router(router_limits_api_router)  # [Main window update chat]
app.include_router(router_lineage_api_router)  # [Main window update chat]
app.include_router(router_logs_api_router)  # [Main window update chat]
app.include_router(router_log_control_api_router)  # [Main window update chat]
app.include_router(router_lore_api_router)  # [Main window update chat]
app.include_router(router_market_api_router)  # [Main window update chat]
app.include_router(router_mass_edit_api_router)  # [Main window update chat]
app.include_router(router_meta_api_router)  # [Main window update chat]
app.include_router(router_meta_backcompat_api_router)  # [Main window update chat]
app.include_router(router_metrics_api_router)  # [Main window update chat]
app.include_router(router_music_mood_api_router)  # [Main window update chat]
app.include_router(router_npc_api_router)  # [Main window update chat]
app.include_router(router_orchestrator_api_router)  # [Main window update chat]
app.include_router(router_packager_api_router)  # [Main window update chat]
app.include_router(router_persona_api_router)  # [Main window update chat]
app.include_router(router_playground_api_router)  # [Main window update chat]
app.include_router(router_playground_compose_api_router)  # [Main window update chat]
app.include_router(router_plugins_api_router)  # [Main window update chat]
app.include_router(router_plugin_api_router)  # [Main window update chat]
app.include_router(router_projects_api_router)  # [Main window update chat]
app.include_router(router_render_api_router)  # [Main window update chat]
app.include_router(router_render_bridge_api_router)  # [Main window update chat]
app.include_router(router_render_feedback_api_router)  # [Main window update chat]
app.include_router(router_render_v07_api_router)  # [Main window update chat]
app.include_router(router_replay_api_router)  # [Main window update chat]
app.include_router(router_replay_memory_api_router)  # [Main window update chat]
app.include_router(router_roleplay_api_router)  # [Main window update chat]
app.include_router(router_scanner_api_router)  # [Main window update chat]
app.include_router(router_scenes_api_router)  # [Main window update chat]
app.include_router(router_scene_analyzer_api_router)  # [Main window update chat]
app.include_router(router_scene_api_router)  # [Main window update chat]
app.include_router(router_scene_director_api_router)  # [Main window update chat]
app.include_router(router_scene_persistence_api_router)  # [Main window update chat]
app.include_router(r_scheduler_api_router)  # [Main window update chat]
app.include_router(router_search_api_router)  # [Main window update chat]
app.include_router(router_secure_api_router)  # [Main window update chat]
app.include_router(router_sessions_api_router)  # [Main window update chat]
app.include_router(router_settings_api_router)  # [Main window update chat]
app.include_router(router_snapshot_api_router)  # [Main window update chat]
app.include_router(router_system_api_router)  # [Main window update chat]
app.include_router(router_telemetry_api_router)  # [Main window update chat]
app.include_router(router_translation_api_router)  # [Main window update chat]
app.include_router(router_trash_api_router)  # [Main window update chat]
app.include_router(router_tts_api_router)  # [Main window update chat]
app.include_router(router_v1_system_api_router)  # [Main window update chat]
app.include_router(router_versioning_api_router)  # [Main window update chat]
app.include_router(router_voice_api_router)  # [Main window update chat]
app.include_router(router_webhooks_api_router)  # [Main window update chat]
app.include_router(router_wf_runtime_api_router)  # [Main window update chat]
app.include_router(router_workflows_api_router)  # [Main window update chat]
app.include_router(router_render_api_router)  # [Main window update chat]
app.include_router(router_roleplay_api_router)  # [Main window update chat]
app.include_router(router_roleplay_correction_api_router)  # [Main window update chat]
app.include_router(router_sampler_api_router)  # [Main window update chat]
app.include_router(router_nodes_router)  # [Main window update chat]
app.include_router(router_st_bridge_router)  # [Main window update chat]
              default_response_class=_DEFAULT) if _DEFAULT else FastAPI(title="ComfyVN", version="0.8.0")

register_exception_handlers(app)

# -------------------------------------------------------
# Deprecation Header Middleware
# -------------------------------------------------------
@app.middleware("http")
async def legacy_deprecation_headers(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path or "/"
    if not path.startswith("/v1/"):
        resp.headers.setdefault("Deprecation", "true")
        resp.headers.setdefault("Link", f"</v1{path}>; rel=\"successor-version\"")
    return resp

# -------------------------------------------------------
# Middleware Stack
# -------------------------------------------------------
cors = os.getenv("CORS_ORIGINS", "*")
allow = ["*"] if cors == "*" else [x.strip() for x in cors.split(",") if x.strip()]

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=allow, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(TimeoutMiddleware)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TimingMiddleware)

# -------------------------------------------------------
# Core Managers
# -------------------------------------------------------
event_bus = EventBus()
plugins = PluginManager()
try:
    from comfyvn.plugins.echo import plugin as echo_plugin
    plugins.register(echo_plugin)
except Exception:
    pass

job_manager = JobManager(event_bus=event_bus, plugins=plugins)
render_manager = RenderManager()
orchestrator = Orchestrator()
_set_rm(render_manager)
_set_wf_jm(job_manager)

app.state.event_bus = event_bus
app.state.plugins = plugins
app.state.job_manager = job_manager
app.state.render_manager = render_manager
app.state.orchestrator = orchestrator
from comfyvn.core.event_hub import EventHub
from comfyvn.core.flow_registry import r as r_flow_registry_router  # [Main window update chat]
from comfyvn.core.health import r as r_health_router  # [Main window update chat]
from comfyvn.core.ops_routes import r as r_ops_routes_router  # [Main window update chat]
from comfyvn.server.jobs_api import jobs as jobs_jobs_api_router  # [Main window update chat]
from comfyvn.server.jobs_api import root as root_jobs_api_router  # [Main window update chat]
from comfyvn.server.snapshots_api import router as router_snapshots_api_router  # [Main window update chat]
from comfyvn.server.modules.admin_api import router as router_admin_api_router  # [Main window update chat]
from comfyvn.server.modules.agent_api import router as router_agent_api_router  # [Main window update chat]
from comfyvn.server.modules.artifacts_api import router as router_artifacts_api_router  # [Main window update chat]
from comfyvn.server.modules.assets_api import router as router_assets_api_router  # [Main window update chat]
from comfyvn.server.modules.assets_api_ex import router as router_assets_api_ex_router  # [Main window update chat]
from comfyvn.server.modules.assets_pipeline_api import router as router_assets_pipeline_api_router  # [Main window update chat]
from comfyvn.server.modules.asset_store_api import router as router_asset_store_api_router  # [Main window update chat]
from comfyvn.server.modules.audit_api import router as router_audit_api_router  # [Main window update chat]
from comfyvn.server.modules.auth_api import router as router_auth_api_router  # [Main window update chat]
from comfyvn.server.modules.auth_oidc_api import router as router_auth_oidc_api_router  # [Main window update chat]
from comfyvn.server.modules.branchmap_api import router as router_branchmap_api_router  # [Main window update chat]
from comfyvn.server.modules.bridgehub_api import router as router_bridgehub_api_router  # [Main window update chat]
from comfyvn.server.modules.bridge_api import router as router_bridge_api_router  # [Main window update chat]
from comfyvn.server.modules.characters_api import router as router_characters_api_router  # [Main window update chat]
from comfyvn.server.modules.collab_api import router as router_collab_api_router  # [Main window update chat]
from comfyvn.server.modules.comfyui_bridge_api import router as router_comfyui_bridge_api_router  # [Main window update chat]
from comfyvn.server.modules.comfy_bridge_api import router as router_comfy_bridge_api_router  # [Main window update chat]
from comfyvn.server.modules.continuity_api import router as router_continuity_api_router  # [Main window update chat]
from comfyvn.server.modules.control_api import router as router_control_api_router  # [Main window update chat]
from comfyvn.server.modules.db_api import router as router_db_api_router  # [Main window update chat]
from comfyvn.server.modules.devices_api import router as router_devices_api_router  # [Main window update chat]
from comfyvn.server.modules.device_api import router as router_device_api_router  # [Main window update chat]
from comfyvn.server.modules.diagnostics_api import router as router_diagnostics_api_router  # [Main window update chat]
from comfyvn.server.modules.env_api import router as router_env_api_router  # [Main window update chat]
from comfyvn.server.modules.events_api import router as router_events_api_router  # [Main window update chat]
from comfyvn.server.modules.events_bus_api import router as router_events_bus_api_router  # [Main window update chat]
from comfyvn.server.modules.events_ws_api import router as router_events_ws_api_router  # [Main window update chat]
from comfyvn.server.modules.export_bundle_api import router as router_export_bundle_api_router  # [Main window update chat]
from comfyvn.server.modules.export_hook import router as router_export_hook_router  # [Main window update chat]
from comfyvn.server.modules.export_scene_api import router as router_export_scene_api_router  # [Main window update chat]
from comfyvn.server.modules.godot_proxy_api import router as router_godot_proxy_api_router  # [Main window update chat]
from comfyvn.server.modules.gui_api import router as router_gui_api_router  # [Main window update chat]
from comfyvn.server.modules.health_api import router as router_health_api_router  # [Main window update chat]
from comfyvn.server.modules.home_api import router as router_home_api_router  # [Main window update chat]
from comfyvn.server.modules.i18n_api import router as router_i18n_api_router  # [Main window update chat]
from comfyvn.server.modules.importers_api import router as router_importers_api_router  # [Main window update chat]
from comfyvn.server.modules.import_api import router as router_import_api_router  # [Main window update chat]
from comfyvn.server.modules.import_vn_v07_api import router as router_import_vn_v07_api_router  # [Main window update chat]
from comfyvn.server.modules.jobs_api import router as router_jobs_api_router  # [Main window update chat]
from comfyvn.server.modules.jobs_backcompat_api import router as router_jobs_backcompat_api_router  # [Main window update chat]
from comfyvn.server.modules.jobs_health_api import router as router_jobs_health_api_router  # [Main window update chat]
from comfyvn.server.modules.jobs_test_api import router as router_jobs_test_api_router  # [Main window update chat]
from comfyvn.server.modules.job_orchestrator_api import router as router_job_orchestrator_api_router  # [Main window update chat]
from comfyvn.server.modules.limits_api import router as router_limits_api_router  # [Main window update chat]
from comfyvn.server.modules.lineage_api import router as router_lineage_api_router  # [Main window update chat]
from comfyvn.server.modules.logs_api import router as router_logs_api_router  # [Main window update chat]
from comfyvn.server.modules.log_control_api import router as router_log_control_api_router  # [Main window update chat]
from comfyvn.server.modules.lore_api import router as router_lore_api_router  # [Main window update chat]
from comfyvn.server.modules.market_api import router as router_market_api_router  # [Main window update chat]
from comfyvn.server.modules.mass_edit_api import router as router_mass_edit_api_router  # [Main window update chat]
from comfyvn.server.modules.meta_api import router as router_meta_api_router  # [Main window update chat]
from comfyvn.server.modules.meta_backcompat_api import router as router_meta_backcompat_api_router  # [Main window update chat]
from comfyvn.server.modules.metrics_api import router as router_metrics_api_router  # [Main window update chat]
from comfyvn.server.modules.music_mood_api import router as router_music_mood_api_router  # [Main window update chat]
from comfyvn.server.modules.npc_api import router as router_npc_api_router  # [Main window update chat]
from comfyvn.server.modules.orchestrator_api import router as router_orchestrator_api_router  # [Main window update chat]
from comfyvn.server.modules.packager_api import router as router_packager_api_router  # [Main window update chat]
from comfyvn.server.modules.persona_api import router as router_persona_api_router  # [Main window update chat]
from comfyvn.server.modules.playground_api import router as router_playground_api_router  # [Main window update chat]
from comfyvn.server.modules.playground_compose_api import router as router_playground_compose_api_router  # [Main window update chat]
from comfyvn.server.modules.plugins_api import router as router_plugins_api_router  # [Main window update chat]
from comfyvn.server.modules.plugin_api import router as router_plugin_api_router  # [Main window update chat]
from comfyvn.server.modules.projects_api import router as router_projects_api_router  # [Main window update chat]
from comfyvn.server.modules.render_api import router as router_render_api_router  # [Main window update chat]
from comfyvn.server.modules.render_bridge_api import router as router_render_bridge_api_router  # [Main window update chat]
from comfyvn.server.modules.render_feedback_api import router as router_render_feedback_api_router  # [Main window update chat]
from comfyvn.server.modules.render_v07_api import router as router_render_v07_api_router  # [Main window update chat]
from comfyvn.server.modules.replay_api import router as router_replay_api_router  # [Main window update chat]
from comfyvn.server.modules.replay_memory_api import router as router_replay_memory_api_router  # [Main window update chat]
from comfyvn.server.modules.roleplay_api import router as router_roleplay_api_router  # [Main window update chat]
from comfyvn.server.modules.scanner_api import router as router_scanner_api_router  # [Main window update chat]
from comfyvn.server.modules.scenes_api import router as router_scenes_api_router  # [Main window update chat]
from comfyvn.server.modules.scene_analyzer_api import router as router_scene_analyzer_api_router  # [Main window update chat]
from comfyvn.server.modules.scene_api import router as router_scene_api_router  # [Main window update chat]
from comfyvn.server.modules.scene_director_api import router as router_scene_director_api_router  # [Main window update chat]
from comfyvn.server.modules.scene_persistence_api import router as router_scene_persistence_api_router  # [Main window update chat]
from comfyvn.server.modules.scheduler_api import r as r_scheduler_api_router  # [Main window update chat]
from comfyvn.server.modules.search_api import router as router_search_api_router  # [Main window update chat]
from comfyvn.server.modules.secure_api import router as router_secure_api_router  # [Main window update chat]
from comfyvn.server.modules.sessions_api import router as router_sessions_api_router  # [Main window update chat]
from comfyvn.server.modules.settings_api import router as router_settings_api_router  # [Main window update chat]
from comfyvn.server.modules.snapshot_api import router as router_snapshot_api_router  # [Main window update chat]
from comfyvn.server.modules.system_api import router as router_system_api_router  # [Main window update chat]
from comfyvn.server.modules.telemetry_api import router as router_telemetry_api_router  # [Main window update chat]
from comfyvn.server.modules.translation_api import router as router_translation_api_router  # [Main window update chat]
from comfyvn.server.modules.trash_api import router as router_trash_api_router  # [Main window update chat]
from comfyvn.server.modules.tts_api import router as router_tts_api_router  # [Main window update chat]
from comfyvn.server.modules.v1_system_api import router as router_v1_system_api_router  # [Main window update chat]
from comfyvn.server.modules.versioning_api import router as router_versioning_api_router  # [Main window update chat]
from comfyvn.server.modules.voice_api import router as router_voice_api_router  # [Main window update chat]
from comfyvn.server.modules.webhooks_api import router as router_webhooks_api_router  # [Main window update chat]
from comfyvn.server.modules.wf_runtime_api import router as router_wf_runtime_api_router  # [Main window update chat]
from comfyvn.server.modules.workflows_api import router as router_workflows_api_router  # [Main window update chat]
from comfyvn.server.modules.roleplay.render_api import router as router_render_api_router  # [Main window update chat]
from comfyvn.server.modules.roleplay.roleplay_api import router as router_roleplay_api_router  # [Main window update chat]
from comfyvn.server.modules.roleplay.roleplay_correction_api import router as router_roleplay_correction_api_router  # [Main window update chat]
from comfyvn.server.modules.roleplay.sampler_api import router as router_sampler_api_router  # [Main window update chat]
from comfyvn.server.routes.nodes import router as router_nodes_router  # [Main window update chat]
from comfyvn.server.routes.st_bridge import router as router_st_bridge_router  # [Main window update chat]
app.state.event_hub = EventHub()

# -------------------------------------------------------
# Router Mounts
# -------------------------------------------------------
# --- Core + Health ---
app.include_router(AgentRouter, prefix="/agent", tags=["agent"])
app.include_router(OrchestratorRouter, prefix="/orchestrator", tags=["orchestrator"])
app.include_router(TelemetryRouter, prefix="/telemetry", tags=["telemetry"])
app.include_router(HealthRouter)
app.include_router(SystemRouter, prefix="/system", tags=["system"])
app.include_router(V1SystemRouter, prefix="/v1", tags=["v1"])
app.include_router(SecureRouter, tags=["secure"])
app.include_router(JobsHealthRouter, prefix="/jobs-health", tags=["jobs-health"])
app.include_router(MetricsRouter, prefix="/metrics", tags=["metrics"])
app.include_router(RenderRouter)
app.include_router(HomeRouter)
app.include_router(DiagnosticsRouter)
app.include_router(SceneIORouter, prefix="/sceneio", tags=["sceneio"])
app.include_router(LogControlRouter)

# --- Jobs / Workflows ---
app.include_router(PackagerRouter, prefix="/packager", tags=["packager"])
app.include_router(JobsRouterFactory(job_manager, event_bus, plugins), prefix="/jobs", tags=["jobs"])
app.include_router(WorkflowsRouter, prefix="/workflows", tags=["workflows"])
app.include_router(EventsRouter, prefix="/events", tags=["events"])
app.include_router(ExportBundleRouter, prefix="/export", tags=["export"])

# --- Optional / Extended ---
app.include_router(BridgeHubRouter, prefix="/bridgehub", tags=["bridgehub"])
app.include_router(SessionsRouter, prefix="/sessions", tags=["sessions"])
app.include_router(AssetsXRouter, prefix="/assetsx", tags=["assetsx"])
app.include_router(PlaygroundRouter, prefix="/playground", tags=["playground"])
app.include_router(TranslationRouter, prefix="/translate", tags=["translate"])
app.include_router(NpcRouter, prefix="/npc", tags=["npc"])
app.include_router(ControlRouter, prefix="/control", tags=["control"])
app.include_router(SchedulerRouter(None), prefix="/scheduler", tags=["scheduler"])
app.include_router(AssetStoreRouter, prefix="/asset-store", tags=["asset-store"])
app.include_router(WebhooksRouter, prefix="/webhooks", tags=["webhooks"])
app.include_router(BridgeRouter, prefix="/bridge", tags=["bridge"])
app.include_router(RoleplayRouter, prefix="/roleplay", tags=["roleplay"])
app.include_router(MassEditRouter, prefix="/mass-edit", tags=["mass-edit"])
app.include_router(EnvRouter, prefix="/env", tags=["env"])
app.include_router(SceneAnalyzerRouter, prefix="/analyze", tags=["analyze"])
app.include_router(GodotProxyRouter,    prefix="/play3d", tags=["play3d"])
app.include_router(TTSRouter,           prefix="/voice",  tags=["voice"])
app.include_router(MusicMoodRouter,     prefix="/music",  tags=["music"])
app.include_router(I18nRouter,          prefix="/i18n",   tags=["i18n"])
app.include_router(ReplayRouter,        prefix="/replay", tags=["replay"])
app.include_router(BranchMapRouter,     prefix="/branchmap", tags=["branchmap"])
app.include_router(ContinuityRouter,    prefix="/continuity", tags=["continuity"])
app.include_router(MarketRouter,        prefix="/market", tags=["market"])
app.include_router(EventsRealtimeRouter, prefix="/events", tags=["events-realtime"])
app.include_router(DevicesRouter, prefix='/devices', tags=['devices'])
app.include_router(PluginAdminRouter, prefix='/plugins', tags=['plugins'])
app.include_router(GuiRouter,      prefix='/gui', tags=['gui'])
app.include_router(SettingsRouter, prefix='/settings', tags=['settings'])
app.include_router(AdminRouter, prefix="/admin", tags=["admin"])
app.include_router(JobOrchestratorRouter, prefix="/jobs-orch", tags=["jobs-orch"])
app.include_router(RenderFeedbackRouter, prefix="/render-feedback", tags=["render-feedback"])

# -------------------------------------------------------
# Static Mounts
# -------------------------------------------------------
app.mount("/studio", StaticFiles(directory="comfyvn/studio", html=True), name="studio")
app.mount("/asset-store/static", StaticFiles(directory="data/assets", html=False), name="assets")

# -------------------------------------------------------
# Plugin Watcher
# -------------------------------------------------------
def _watch_plugins():
    try:
        from watchfiles import watch
        for _ in watch("./data/plugins", stop_event=None):
            plugins.reload_from_dir("./data/plugins")
    except Exception:
        pass

threading.Thread(target=_watch_plugins, daemon=True).start()

# -------------------------------------------------------
# Shutdown Hook
# -------------------------------------------------------
@app.on_event("shutdown")
def save_all():
    """Persist transient runtime state on shutdown."""
    try:
        from comfyvn.core.state_manager import StateManager
        state = StateManager()
    except Exception:
        state = None

    # Save jobs
    try:
        if hasattr(app.state, "job_manager") and hasattr(app.state.job_manager, "snapshot"):
            data = app.state.job_manager.snapshot()
            if state:
                state.save("jobs", data)
    except Exception:
        pass

    # Save renders
    try:
        if hasattr(app.state, "render_manager") and hasattr(app.state.render_manager, "snapshot"):
            data = app.state.render_manager.snapshot()
            if state:
                state.save("renders", data)
    except Exception:
        pass

    # Save registry
    try:
        if hasattr(app.state, "system_registry") and hasattr(app.state.system_registry, "info"):
            data = app.state.system_registry.info()
            if state:
                state.save("registry", data)
    except Exception:
        pass
        
@app.get("/health")
def health():
    return {"ok": True, "version": "0.5.0"}


# -------------------------------------------------------
# Agent background thread
# -------------------------------------------------------
def _start_agent_thread(app):
    import threading, time
    def _agent_loop():
        while True:
            try:
                orch = getattr(app.state, "orchestrator", None)
                if orch:
                    orch.tick(app)
            except Exception:
                pass
            time.sleep(1.0)
    t = threading.Thread(target=_agent_loop, daemon=True)
    t.start()


# -------------------------------------------------------
# Extended Scene + Bridge Routers
# -------------------------------------------------------
app.include_router(LoreRouter, prefix="/lore", tags=["lore"])
app.include_router(PersonaRouter, prefix="/persona", tags=["persona"])
app.include_router(VoiceRouter, prefix="/voice", tags=["voice"])
app.include_router(SceneRouter, prefix="/scene", tags=["scene"])
app.include_router(RenderBridgeRouter, prefix="/render", tags=["render-bridge"])
app.include_router(PlaygroundComposeRouter, prefix="/playground", tags=["playground-compose"])
app.include_router(ExportSceneRouter, prefix="/export", tags=["export-scene"])
app.include_router(DeviceRouter, prefix="/devices", tags=["devices"])
app.include_router(AssetsPipelineRouter, prefix="/assets", tags=["assets"])
app.include_router(ComfyUIBridgeRouter, prefix="/comfyui", tags=["comfyui"])
app.include_router(DirectorRouter, prefix="/director", tags=["director"])
app.include_router(EventsBusRouter, prefix="/events-bus", tags=["events-bus"])

# v0.5 DB routes
app.include_router(DBv05Router, prefix="/db", tags=["db-v05"])
app.include_router(EventsV05Router, prefix="/events-bus", tags=["events-v05"])
app.include_router(JobsV05Router, prefix="/jobs", tags=["jobs-v05"])
app.include_router(SettingsV06Router, prefix="/settings", tags=["settings-v06"])
app.include_router(ExportV06Router, prefix="/export", tags=["export-v06"])
app.include_router(RenderV07Router, prefix="/render", tags=["render-v07"])
app.include_router(ImportV07Router, prefix="/import", tags=["import-v07"])