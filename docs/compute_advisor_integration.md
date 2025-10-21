# Compute Advisor Integration – Architecture & Compatibility Guide

This note explains how ComfyVN’s compute advisor operates, what metadata it
expects, and how to make the system compatible with third-party GPU services
when you do not yet have an active subscription or live credentials.

## Core architecture

- **Provider registry (`comfyvn/core/compute_registry.py`)**  
  Maintains the list of local and remote compute endpoints. Templates are
  generated from curated provider profiles and expose JSON schemas for GUI or
  API onboarding.

- **GPU manager (`comfyvn/core/gpu_manager.py`)**  
  Discovers local GPUs/CPUs and surfaces remote provider health. It is the
  authoritative source of devices for `/compute/advise` and `/api/gpu/*`.

- **Compute advisor (`comfyvn/core/compute_advisor.py`)**  
  Analyses importer workload metadata (VRAM needs, asset sizes, cached
  ComfyUI workflows, translation pipeline requirements, runtime/budget hints)
  and scores providers. It returns:
  - `choice`: gpu/remote/cpu
  - `remote_candidate`: provider metadata + policy hints + estimated cost
  - `analysis`: intermediate heuristics so GUIs can render explanations
  - `job_summary`: minimal payload for importer/scheduler audit logs

- **Public APIs (`comfyvn/server/modules/compute_api.py`,
  `comfyvn/server/modules/gpu_api.py`)**  
  `/compute/advise` and `/api/gpu/advise` wrap GPU manager + advisor results.
  Use these endpoints when integrating scheduling workflows or GUI components.

## Workload payload expectations

When calling `/compute/advise` or the Python `advise()` helper, supply the
following structure (fields optional but recommended):

```jsonc
{
  "requirements": {
    "type": "cg_batch | voice_synthesis | translation | ...",
    "min_vram_gb": 24,
    "estimated_minutes": 180
  },
  "assets": [
    {"name": "scene_cache.tar", "size_mb": 2400}
  ],
  "workflows": [
    {"id": "cg-upscale", "cached": false, "persist_outputs": true}
  ],
  "budget": {
    "limit_usd": 20,
    "mode": "cost_saver | balanced | speed"
  },
  "pipeline": {
    "translation": {"requires_gpu": true}
  }
}
```

The advisor will infer VRAM floor, burst/batch mode, and persistent storage
requirements from these fields and match them to provider metadata.

## Provider registration schema

Each provider entry in `providers.json` follows:

```jsonc
{
  "id": "runpod",
  "name": "RunPod",
  "kind": "remote",
  "service": "runpod",
  "base_url": "https://api.runpod.io/v2/",
  "active": true,
  "priority": 10,
  "meta": {
    "min_vram_gb": 12,
    "cost": {"hourly_usd": 0.46, "billing_increment_minutes": 1},
    "supports_persistent_storage": false,
    "policy_hints": {
      "voice_synthesis": "Burst-friendly for quick TTS jobs."
    },
    "preferred_workloads": ["voice_synthesis"]
  },
  "config": {"api_key": "RUNPOD_API_KEY"},
  "last_health": {"ok": true, "ts": 0}
}
```

When you do not have live credentials, keep `config` empty or populate with
placeholder values. The advisor will still use `meta` to suggest compatible
providers for workloads.

## Managing provider catalogs

- `POST /api/providers/create` lets you instantiate a provider directly from a
  curated template (`template_id`) while supplying overrides for URLs, names,
  and configuration secrets.
- `POST /api/providers/import` ingests a JSON export. Use `replace=true` to
  reset the registry or `overwrite=false` to skip providers that already exist.
- `GET /api/providers/export` returns the current registry. Secrets are removed
  by default; pass `include_secrets=true` only when generating internal backups
  from localhost or when `COMFYVN_ALLOW_SECRET_EXPORT=1`.
- `DELETE /api/providers/remove/{id}` cleans up entries (the built-in `local`
  provider is protected from deletion).

These APIs power GUI flows (import/export buttons) and enable scripted CI/CD
pipelines to seed environments with curated remote GPU presets.

## External documentation directory

The curated provider profile library cross-references official documentation.
Use the following resources to understand authentication models and API
surface before subscribing:

| Provider | Documentation | Key compatibility notes |
|----------|---------------|-------------------------|
| RunPod | https://docs.runpod.io/docs/introduction | REST API, bearer API key, serverless & dedicated pods. |
| Vast.ai | https://vast.ai/docs/ | Marketplace bids, specify `machine_id`, image, and price ceiling. |
| Lambda Labs | https://cloud.lambdalabs.com/api/docs | JWT/bearer API key, region selection required. |
| AWS EC2 | https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/accelerated-computing-instances.html | Use IAM keys/roles; consider spot for pricing; manage security groups. |
| Azure NV | https://learn.microsoft.com/azure/virtual-machines/sizes-gpu | Service principals (AAD); monitor quota per region. |
| CoreWeave | https://docs.coreweave.com/ | Kubernetes-native workloads; authenticate with API key + org ID. |
| Google Cloud | https://cloud.google.com/compute/docs/gpus | Service account JSON; enable Compute Engine API; align bucket region. |
| Paperspace | https://docs.paperspace.com/core/api-reference/ | API key + project; persistent volume setup for caches. |
| unRAID | https://docs.unraid.net/ | Expose Docker/SSH endpoints; ensure TLS for remote control. |
| On-Prem SSH | OpenSSH docs: https://www.openssh.com/manual.html | Provide host, SSH key, optional NFS mounts for datasets. |

## Preparing for compatibility

1. **Mock credentials & dry runs**  
   Populate provider registry entries with placeholder credentials and run
   `/api/gpu/advise` to verify recommendations without launching jobs.

2. **Health check adapters**  
   Implement health checks in `comfyvn/core/compute_providers.py` using the
   REST endpoints documented above. Mark providers inactive when checks fail so
   the advisor deprioritises them.

3. **Cost governance**  
   Even without subscriptions, capture public pricing in provider metadata.
   The advisor uses `hourly_usd` and `billing_increment_minutes` to estimate
   job costs.

4. **Residency & legal mapping**  
   Extend provider metadata with `regions`, `egress_notice`, or custom policy
   fields. The documentation in `docs/remote_gpu_services.md` explains how to
   surface warnings in importer job summaries.

5. **Future subscriptions**  
   Once credentials are issued, update `config` with secrets (API keys, client
   IDs). No code changes are required—the advisor will immediately begin
  testing remote providers during health checks and workflow scheduling.

## Validation checklist

- [ ] `/api/providers/templates` lists the provider with expected auth fields.
- [ ] `/api/gpu/list` shows remote providers with `available` status derived
      from health checks (false until credentials validated).
- [ ] `/compute/advise` returns `remote_candidate` with cost estimate and
      policy hints based on workload metadata.
- [ ] Job summaries (from importer/scheduler) record `job_summary` data for
      audit logs and user-facing explanations.

Use this guide to stage integrations and documentation reviews before
committing to a provider subscription. Once live credentials are obtained,
replace placeholders and rerun the validation checklist.
