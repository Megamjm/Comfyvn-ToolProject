# Render Grid Integration Notes (ComfyVN v0.7)
- Default adapters are stubs.
- When ready to integrate real providers, start with `comfyvn/core/compute_providers.py`.
- Each provider has a function `service_send()` placeholder.
- Extend it using the API docs of chosen cloud GPU service.
- Update `/render/targets` to include your auth keys and preferred endpoints.
- After implementing, run `python tools/doctor_v07.py` to confirm dispatch.
