# Remote GPU Services – Integration Notes

ComfyVN schedules heavy importer workloads (voice synthesis, CG remix, translation
assists) across local and remote devices. Use this guide when exposing providers
through `/api/providers/*` and the compute advisor.

## Curated providers

| Provider   | API style            | Notes |
|------------|----------------------|-------|
| RunPod     | REST + API key       | Expose preset templates (VRAM, $/hr). Support webhook or polling for job status. |
| Vast.ai    | REST (marketplace)   | Requires bid + instance spec; provide helper to prefill compatible images (Docker). |
| Lambda Labs| REST                 | Similar to RunPod; include region + quota checks. |
| AWS EC2    | AWS SDK / boto       | Offer curated AMIs (e.g., Deep Learning Base) and security-group guidance. |
| Azure NV   | Azure SDK            | Support quota discovery and stop/resume to reduce cost. |
| Paperspace | REST + API key       | Good for sustained workloads; provide container name + persistent storage path. |
| unRAID     | SSH / Docker API     | Target on-prem clusters; use SSH tunnel with docker-compose templates. |
| Custom SSH | SSH command execution| Allow manual configuration (hostname, GPU ID, mount points). |

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

## Legal & data residency

- Warn users when content leaves their machine; highlight provider regions.
- Flag non-open-source assets in summaries so users can review licensing before
  uploading to remote services.

## Next steps

- Build provider-specific adapters under `comfyvn/core/compute_providers.py`.
- Extend GUI settings to include a "Remote GPU" tab listing curated providers.
- Log job/device assignments to `logs/compute_advisor.log` for troubleshooting.
