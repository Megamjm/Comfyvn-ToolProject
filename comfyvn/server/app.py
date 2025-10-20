from __future__ import annotations
import os
from fastapi import FastAPI

# Logging Setup
setup_logging()

try:
    from fastapi.responses import ORJSONResponse as _ORJSON
    _DEFAULT = _ORJSON
except Exception:
    _DEFAULT = None

app = FastAPI(title="ComfyVN", version="0.8.0")

# Router includes (generated elsewhere in file)
app.include_router(r_flow_registry_router)
app.include_router(r_health_router)
app.include_router(r_ops_routes_router)
app.include_router(jobs_jobs_api_router)
app.include_router(root_jobs_api_router)
app.include_router(router_snapshots_api_router)
app.include_router(router_admin_api_router)
app.include_router(router_agent_api_router)
app.include_router(router_artifacts_api_router)
app.include_router(router_assets_api_router)
app.include_router(router_assets_api_ex_router)
app.include_router(router_assets_pipeline_api_router)
app.include_router(router_asset_store_api_router)
app.include_router(router_audit_api_router)
app.include_router(router_auth_api_router)
app.include_router(router_auth_oidc_api_router)
app.include_router(router_branchmap_api_router)
app.include_router(router_bridgehub_api_router)
app.include_router(router_bridge_api_router)
app.include_router(router_characters_api_router)
app.include_router(router_collab_api_router)
app.include_router(router_comfyui_bridge_api_router)
app.include_router(router_comfy_bridge_api_router)
app.include_router(router_continuity_api_router)
app.include_router(router_control_api_router)
app.include_router(router_db_api_router)
app.include_router(router_devices_api_router)
app.include_router(router_device_api_router)
app.include_router(router_diagnostics_api_router)
app.include_router(router_env_api_router)
