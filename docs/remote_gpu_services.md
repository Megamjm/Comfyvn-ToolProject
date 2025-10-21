# Remote GPU Services – Integration Notes

ComfyVN schedules heavy importer workloads (voice synthesis, CG remix, translation
assists) across local and remote devices. Use this guide when exposing providers
through `/api/providers/*` and the compute advisor.

## Curated providers

Compute advisor now consumes a curated profile library (`comfyvn/core/provider_profiles.py`) to prefill
authentication fields, VRAM expectations, pricing hints, and importer policy notes.

For a deeper architecture walkthrough and compatibility checklist, see
`docs/compute_advisor_integration.md`.

| Provider      | Auth fields                                          | Default GPU | Min VRAM | Cost hint*     | Policy highlight |
|---------------|------------------------------------------------------|-------------|----------|----------------|------------------|
| RunPod        | `api_key`                                            | A10G        | 12 GB    | ~$0.46/hr      | Burst-friendly for voice/TTS jobs. |
| Vast.ai       | `api_key`                                            | RTX 4090    | 16 GB    | marketplace    | High VRAM market nodes for CG batches. |
| Lambda Labs   | `api_key`                                            | A100        | 24 GB    | ~$1.10/hr      | Multi-hour CG bakes, diffusion upscales. |
| AWS EC2       | `access_key`, `secret_key`, `region`                 | g5.xlarge   | 24 GB    | ~$1.05/hr      | Spot fleets for render farms; mind egress. |
| Azure NV      | `tenant_id`, `client_id`, `client_secret`, `subscription_id` | NC4as_T4_v3 | 16 GB    | ~$1.00/hr      | Residency-aware translation + CG jobs. |
| CoreWeave     | `api_key`, `organization_id`                         | A40         | 24 GB    | ~$0.95/hr      | Kubernetes clusters for CG + realtime voice. |
| Google Cloud  | `project_id`, `service_account_json`, `region`       | A2 (L4/L40) | 16 GB    | ~$0.85/hr      | Keep GCS + Translation API co-located. |
| Paperspace    | `api_key`, `project`                                 | A4000       | 16 GB    | ~$0.78/hr      | Persistent volumes for importer cache. |
| unRAID / LAN  | `endpoint`, `api_token`                              | local       | 8 GB     | $0             | Low-latency LAN renders, data stays on-prem. |
| On-Prem SSH   | `hostname`, `username`, `ssh_key_path`, `nfs_mount`  | custom      | 8 GB     | $0             | Contract-friendly for regulated content. |

\*Costs are indicative. Billing increments are published per provider (RunPod billed per minute, cloud vendors per hour).

Each profile also ships `policy_hints` consumed by `/compute/advise` so importer job summaries surface provider rationale.

## Advisor inputs

- Asset type (sprite, CG, audio) → maps to expected VRAM/compute needs.
- Preferred latency vs. throughput (interactive editing vs. overnight batch).
- User budget caps (optional) from settings.
- Local capability snapshot (GPU list, VRAM, current load).

## Workflow

1. User registers providers via GUI or `/api/providers/register`.
2. `/compute/advise` evaluates workload metadata (import summary, queued
   ComfyUI workflows, translation jobs) and returns:
   ```json
   {
     "choice": "runpod",
     "estimated_cost": "$0.45",
     "reason": "Local GPU has insufficient VRAM (6GB < 12GB required for CG super-res)."
   }
   ```
3. Jobs record selected provider in TaskRegistry meta for audit trail.
4. Provider health checks run periodically; unhealthy providers are skipped with
   warnings surfaced in GUI.

## Provider management API

- `POST /api/providers/create` — instantiate a provider from a curated template,
  supplying overrides for `name`, `base_url`, `config`, or policy metadata.
- `POST /api/providers/register` — create or update a provider definition with
  arbitrary payloads (used by GUI editor).
- `DELETE /api/providers/remove/{id}` — remove user-defined providers (local
  provider remains protected).
- `GET /api/providers/export` — export the current registry to JSON (secrets
  stripped by default). Pass `?include_secrets=true` for internal backups; only
  available from localhost or when `COMFYVN_ALLOW_SECRET_EXPORT=1`.
- `POST /api/providers/import` — import a registry export. Supports `replace`
  and `overwrite` flags to control merges.

Example `create` payload:

```json
{
  "template_id": "runpod",
  "id": "runpod-demo",
  "name": "RunPod Demo",
  "base_url": "https://api.runpod.io/v2/",
  "config": {"api_key": "RUNPOD_KEY"},
  "meta": {"notes": "Demo project"}
}
```

## Legal & data residency

- Warn users when content leaves their machine; highlight provider regions.
- Flag non-open-source assets in summaries so users can review licensing before
  uploading to remote services.
- Respect contractual residency requirements by mapping importer project tags to the
  `regions` metadata contained in each provider profile (cloud regions vs. on-prem).
- Document DPIA or content restrictions for voice synthesis (RunPod/Lambda) and
  localization data (Azure/AWS/GCP) before enabling team-wide presets.

## Third-party onboarding checklist

All remote GPU providers follow the same onboarding skeleton. Adapt the specifics below when
adding a new third-party adapter:

1. **Profile entry** — Add a `ProviderProfile` entry capturing auth fields, default GPU, VRAM floor,
   pricing tier, region hints, and importer policy guidance.
2. **Template sync** — Ensure the registry template merges the profile metadata so `/api/providers/templates`
   exposes auth inputs and cost hints in the GUI.
3. **Credential capture** — Update GUI forms (or CLI payloads) to request the curated auth fields only.
   Surface validation (e.g., AWS STS call, Azure token exchange) before marking a provider active.
4. **Adapter hooks** — Extend `comfyvn/core/compute_providers.py` with submit/cancel/health checks using
   the provider's SDK or REST API. Reuse shared helpers for SSH/NFS staging if available.
5. **Advisor heuristics** — Confirm `/compute/advise` returns the correct `policy_hint`, estimated
   cost, and remote recommendation when importer metadata specifies workload type, asset size,
   or translation pipeline requirements.
6. **Audit trail** — Register data residency and legal notes in the provider profile `metadata` so
   job summaries surface warnings (e.g., content leaves EU, audio processed on shared pods).

## Provider-specific onboarding notes

- **RunPod**: Generate an API key with job scope. Prefill the template pod type and enable auto-stop.
  Configure webhook secret if round-trip status updates are required.
- **Vast.ai**: Use the marketplace search endpoint to filter instances by `min_vram_gb`. Store the
  chosen machine ID and price ceiling in provider metadata for reproducible bidding.
- **Lambda Labs**: Request quota increases for A100 nodes ahead of CG-heavy projects. Persist region
  selection in provider `config` to keep datasets co-located.
- **AWS EC2**: Require IAM user or role with `ec2:RunInstances`, `ec2:Describe*`, and S3 access to the
  asset bucket. Provide security group and subnet defaults in the registry metadata.
- **Azure NV**: Collect subscription and tenant IDs, then test token issuance via MSAL before activation.
  Populate metadata with allowed regions and quota IDs to short-circuit advisor suggestions when quotas lapse.
- **CoreWeave**: Capture organization ID and API key. Create namespace-scoped credentials so jobs can be
  scheduled without full cluster admin rights.
- **Google Cloud**: Store service account JSON and enforce Cloud Storage bucket region alignment.
  Enable the Compute Engine API before running health checks.
- **Paperspace**: Ask for project name and API key, then pre-create a persistent volume for importer caches.
  Advisor will favor Paperspace when workflows rely on cached ComfyUI graphs.
- **unRAID / LAN**: Verify Docker API exposure over HTTPS and register SSH or VPN tunnels if required.
  Advisor marks these nodes cost-free but still checks health endpoints.
- **On-Prem SSH/NFS**: Collect SSH credentials and mount paths. Document compliance requirements and link
  to internal runbooks so teams can validate data handling per client contract.

## Next steps

- Build provider-specific adapters under `comfyvn/core/compute_providers.py`.
- Extend GUI settings to include a "Remote GPU" tab listing curated providers.
- Log job/device assignments to `compute_advisor.log` in the user log directory for troubleshooting.
