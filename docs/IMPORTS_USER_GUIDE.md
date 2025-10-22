# ComfyVN Imports User Guide

This guide walks through the refreshed import workflow that ships with the
“Live Sweep — docks/menu/import/ST” update.

## Import Entry Points

- **Tools → Import → From File…**  
  Pick any supported bundle directly from your operating system’s file picker.
  JSON payloads are sent over the live REST bridge and archives (`.zip`,
  `.stbundle`) are uploaded with the VN Pack importer. A success toast confirms
  the enqueue, and the **Modules → Imports** panel tracks job status.
- **Tools → Import → SillyTavern Chat / Persona JSON / Lore JSON**  
  Shortcut entries that open the Import Manager with the matching SillyTavern
  preset selected. These rely on the `/st/import` API and respect the host/port
  settings configured in the Studio Basics drawer.
- **Tools → Import → FurAffinity Export / Roleplay Transcript**  
  Sends prepared JSON payloads to `/api/imports/furaffinity` and
  `/api/imports/roleplay`. Use the Import Manager to tweak payloads or retry
  failed submissions.

## Supported Formats

| Format / Extension | Target Endpoint | Notes |
| ------------------ | --------------- | ----- |
| `*.json`/`*.jsonl` | `/st/import`    | Provide `type` (`personas`, `worlds`, `chats`) with a `data` array, or pick the type when prompted. |
| `entries.*` JSON   | `/api/imports/roleplay` | Roleplay transcripts exported from SillyTavern or custom tooling. |
| `collection.*` JSON| `/api/imports/furaffinity` | FurAffinity export bundles; include the `collection` array. |
| `.zip`, `.stbundle`| `/import/vnpack/extract` | VN pack archives; extraction results surface in the Imports panel. |

All payloads are persisted under `data/imports/` and catalogued into the job
registry so you can audit or retry via the Imports dock at any time.

## Drag & Drop and Advanced JSON Editing

The Import Manager continues to offer manual editing for advanced users:

1. Open **Tools → Import → SillyTavern Chat…** (or any other preset).
2. Adjust the JSON payload in-place, then click **Send Request** to submit.
3. Use **Copy URL** to hand off the API call to scripts or CI pipelines.

For scripted workflows, POST directly to the endpoints listed above. The
bridge honours the SillyTavern host/port/base configuration stored in
`config/comfyvn.json`.
