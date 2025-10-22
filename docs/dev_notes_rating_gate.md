# Rating Gate & SFW Workflow (2025-11-18)

## Overview

ComfyVN now ships a conservative content rating stub (`comfyvn/rating/classifier_stub.py`) that scores prompts, assets, and exports against an ESRB-style matrix (`E`, `T`, `M`, `Adult`). The classifier favours the highest-risk bucket until a reviewer pins an override. All state, including overrides and acknowledgement tokens, persists under `config/settings/rating/overrides.json` so reviewer decisions survive restarts.

Feature flags:

- `enable_rating_api` (default: true) — exposes the REST surface and enforces gating in prompts/exports.
- `enable_rating_modder_stream` (default: false) — emits rating events on the Modder Hook Bus when enabled.

Toggle flags via `config/comfyvn.json` or `feature_flags.refresh_cache()` in long-lived processes.

## REST API Summary

| Endpoint | Description |
| --- | --- |
| `GET /api/rating/matrix` | Return keyword/tag matrix with NSFW annotations and descriptions. |
| `POST /api/rating/classify` | Score a payload, return `{rating, confidence, reasons, ack_token}`; honours `mode`, `acknowledged`, and optional `ack_token`. |
| `GET /api/rating/overrides` | List reviewer overrides (most recent first). |
| `POST /api/rating/overrides` | Store/update an override with `{item_id, rating, reviewer, reason, scope}`. |
| `DELETE /api/rating/overrides/{item_id}` | Remove a stored override. |
| `POST /api/rating/ack` | Confirm an acknowledgement token with `{token, user, notes?}`. |
| `GET /api/rating/acks` | Retrieve acknowledgement audit history. |

Example classification flow:

```bash
curl -s -X POST http://127.0.0.1:8000/api/rating/classify \
  -H 'Content-Type: application/json' \
  -d '{
        "item_id": "prompt:test",
        "payload": {"text": "Steamy nightclub scene with explicit lyrics"},
        "mode": "sfw"
      }' | jq
# {
#   "ok": true,
#   "item_id": "prompt:test",
#   "allowed": false,
#   "requires_ack": true,
#   "ack_token": "0750f7...",
#   "ack_status": "issued",
#   "rating": {
#     "rating": "Adult",
#     "confidence": 0.85,
#     "nsfw": true,
#     "matched": {"Adult": ["keyword:explicit", "keyword:steamy"]},
#     "source": "classifier",
#     "reasons": ["keyword:explicit", "keyword:steamy"],
#     ...
#   }
# }
```

To proceed, present the warning to the reviewer, call `POST /api/rating/ack` with the issued token, then retry the blocked action with `acknowledged=true` and `ack_token` set to the confirmed token.

## SFW Gate Integration

- **Prompt tooling** — `/api/llm/test-call` evaluates the active message bundle. When SFW is enabled and the rating returns `M` or `Adult`, the route responds with HTTP 423 and the issued `ack_token`. The same payload mirrors back in the success case via `rating_gate` so clients can log or surface the resolved rating.
- **Ren'Py exports** — `RenPyOrchestrator.export` calls the rating service before processing scenes. Gated exports raise HTTP 423 with `detail.gate`; CLI users pass `--rating-ack-token` and `--rating-acknowledged` to honour the same workflow. Export manifests now include `rating` and `rating_gate` entries for downstream audits.
- **Content filters** — `ContentFilter.classify` falls back to the rating service when metadata/tags are inconclusive, ensuring importer previews still surface warnings inside Studio.

## Modder Hooks & Logging

When `enable_rating_modder_stream` is true, the rating service publishes:

- `on_rating_decision` — every classification/evaluation, including `{item_id, rating, nsfw, confidence, mode, matched, ack_status, allowed}`.
- `on_rating_override` — reviewer overrides with `{item_id, rating, reviewer, reason, scope, timestamp, removed}`.
- `on_rating_acknowledged` — ack confirmations with `{token, item_id, action, rating, user, acknowledged_at}`.

Subscribe via `GET /api/modder/hooks` or `ws://…/api/modder/hooks/ws` (topic `modder.on_rating_*`). Overrides and acknowledgements are persisted to disk, while hook history is capped by the shared modder bus queue.

Structured logs land under logger names:

- `comfyvn.rating` — override writes, ack confirmations, fallback errors.
- `comfyvn.server.routes.llm` — HTTP 423 blocks for prompt calls.
- `comfyvn.exporters.renpy_orchestrator` — gating rejections during export.

## Export Manifest Snapshot

`build/renpy_game/export_manifest.json` now contains:

```json
{
  "rating": {
    "item_id": "export:summer_project",
    "rating": "Teen",
    "confidence": 0.7,
    "nsfw": false,
    "source": "classifier",
    "reasons": ["fallback: conservative teen rating"]
  },
  "rating_gate": {
    "mode": "sfw",
    "allowed": true,
    "requires_ack": false,
    "ack_status": "not_required"
  }
}
```

Automation pipelines can now archive the rating alongside provenance sidecars and policy gate state for downstream distribution checks.
