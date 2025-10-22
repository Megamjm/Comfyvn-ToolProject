# Advisory & Modding Notes

This sheet keeps studio contributors and modders aligned on advisory expectations, debug hooks, and the plugin surface exposed by the new scanner pipeline. You remain free to build any stories or assets you want—ComfyVN simply highlights risks so you can accept responsibility before you ship.

## Creative Freedom, Legal Responsibility
- Acknowledge the liability gate once per install through **Studio → Settings → Advisory** or by calling `POST /api/policy/ack`. The acknowledgement records _who_ accepted the terms and when.
- The advisory scanner never deletes content. Instead, it grades findings as `info`, `warn`, or `block`. You decide how to respond, but block-level issues must be cleared (or waived by policy owners) before exports succeed.
- CLI exports (`python scripts/export_bundle.py --project <id>`) surface warnings on stderr and exit with code `2` when blockers remain, ensuring automated pipelines halt until a human signs off.
- Review provenance bundles: `provenance.json` includes scanner findings, making downstream distribution traceable back to the point where the user accepted responsibility.

## Scanner Plugin Surface
- Built-ins live in `comfyvn/advisory/scanner.py`:
  - `spdx_license`: normalises licence strings, warns on share-alike/non-commercial licences, and blocks obvious “no redistribution” terms.
  - `ip_match`: scans scenes/characters/metadata for franchise keywords to prompt manual review.
  - `nsfw_classifier`: optional; register a hook with `register_nsfw_classifier(callable)` to feed asset-level scores. Return `{id, score, severity?, label?, message?}` per asset and the framework will translate to advisory issues.
- Register custom bundle scanners with:
  ```python
  from comfyvn.advisory.scanner import register_scanner_plugin

  def my_checker(context):
      # context is comfyvn.core.advisory_hooks.BundleContext
      if "premium" in (context.metadata or {}):
          yield {
              "target_id": context._target("premium"),
              "kind": "policy",
              "message": "Premium flag present – verify licence tier.",
              "severity": "warn",
              "detail": {"plugin": "my_checker"},
          }

  register_scanner_plugin("my_checker", my_checker)
  ```
- All plugin findings flow through `log_issue`, persist in SQLite, and appear in `/api/advisory/logs` for UI panels.

## Debug Hooks
- Increase verbosity with `COMFYVN_LOG_LEVEL=DEBUG` or `LOG_LEVEL=DEBUG` when launching either the server or Studio shell.
- Advisory-specific logs write under `logs/server.log` with category `comfyvn.advisory.*`.
- Export provenance packs include a mirror of findings. Inspect `build/studio_bundle.zip` → `provenance.json` to double-check what the gate evaluated.
- For asset classifiers, set `COMFYVN_ADVISORY_TRACE=1` (optional helper flag) to emit per-asset decisions while iterating custom hooks.

## API Matrix for Modders
- Advisory core:
  - `POST /api/advisory/scan` – synchronous text scan.
  - `GET /api/advisory/logs?resolved=` – list findings (use `false` for unresolved).
  - `POST /api/advisory/resolve` – mark issues resolved with optional notes.
- Policy gate:
  - `GET /api/policy/status` – current acknowledgement + override flag.
  - `POST /api/policy/ack` – record acknowledgement (Studio uses this).
  - `POST /api/policy/evaluate` – dry-run exports/imports; include `{action, override}`.
  - `GET/POST /api/policy/filters` – manage SFW/Warn/Unrestricted content modes.
  - `POST /api/policy/filter-preview` – test how content would be classified.
- Asset tooling (relevant to provenance and mod packaging):
  - `GET /assets` and `GET /assets/{uid}` – enumerate registry entries.
  - `POST /assets/register` – add media with sidecar metadata.
  - `POST /assets/upload` – ingest files while advisory logs track provenance.

## Workflow Tips
- During development, keep the Advisory panel open in Studio (**Window → Advisory**). It refreshes findings per action and surfaces blockers before you invest in long renders.
- Automation pipelines should check the CLI JSON payload; `blocked: true` means halt. When only warnings remain, include the advisory payload in release notes so reviewers know you accepted the risk.
- Mod submissions should ship their own scanner plugins alongside documentation describing what they enforce. The host user always decides whether to enable those plugins.
- When contributing new hooks, add a short section to this doc (pull request welcome) describing the plugin name, purpose, and any environment variables it expects.
