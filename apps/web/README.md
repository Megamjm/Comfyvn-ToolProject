# ComfyVN Web Surface

Updated: 2025-12-24  
Owner: Studio Desktop / Web

The repository ships a small collection of static admin tools under `comfyvn/studio` that are served by the FastAPI backend. The new **Network / Port Binding** page rounds out the stack by giving contributors a browser-native way to tune the launcher’s host/port authority without editing JSON by hand.

## Pages

- `/studio/index.html` – Scene composer shell (links to assets, scheduler, roleplay panels).
- `/studio/settings/network.html` – Admin-only network binding panel powered by `/api/settings/ports/{get,set,probe}`. Requires a Bearer token with admin scope and mirrors probe output so operators can verify the active binding before restarting the backend.
- `/studio/assets.html`, `/studio/roleplay.html`, `/studio/scheduler.html`, `/studio/env.html` – Legacy single-purpose tools kept for quick diagnostics.

## Network / Port Binding Highlights

- Fetches and persists host, rollover port order, and optional `public_base` overrides via the shared launcher config (`config/comfyvn.json`) and runtime stamp (`.runtime/last_server.json`).
- Provides one-click probe, summarising the “would bind to” base URL plus per-port attempts for debugging firewall conflicts.
- Surfaces ready-to-share curl drills so modders/CI can script against the same endpoints.
- Stores the API base + token locally so repeated visits stay streamlined while still respecting admin-only access.

See `docs/PORTS_ROLLOVER.md` for deep-dive automation notes and `docs/dev_notes_network_ports.md` for contributor-focused implementation details.
