# Legal & Liability Notice

ComfyVN ships with tooling that can ingest user-generated content from external
communities (SillyTavern, FurAffinity, roleplay archives, etc.). Studio
operators **must** ensure contributors understand the liability waiver before
syncing or distributing assets.

## Why the Waiver Exists

- Imported data may include sensitive conversations, likenesses, or third-party
  intellectual property.
- ComfyVN exposes automation hooks that can redistribute content across
  projects, cloud providers, or collaborative branches.
- Some importer presets interact with adult-themed archives; ensuring informed
  consent protects the contributors, studio, and downstream partners.

## Acknowledging the Policy

The studio UI surfaces the waiver via **Settings → Advisory**. For automation
or CI workflows call:

```
POST /api/advisory/ack { "user": "ci-bot", "notes": "pipeline bootstrap" }
```

The acknowledgement is stored under `ack_disclaimer_v1` (plus metadata in
`advisory_ack`) within `config/comfyvn.json`. Health checks and onboarding
flows should confirm this flag before enabling SillyTavern bridging or remote
publishing tasks.

## Recommended Practices

- Record acknowledgement timestamps alongside contributor IDs for audit trails.
- Pair importer access with read-only workspaces until acknowledgements are
  captured.
- Re-run `/api/advisory/ack` whenever the legal text or liability scope
  changes, and bump the version key to invalidate stale consents.
- Reference the waiver inside modding documentation and CONTRIBUTING guides so
  third-party teams inherit the same expectations.
