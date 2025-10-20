ComfyUI Music Remix Workflow
============================

This guide outlines a reference workflow for generating or remixing music with ComfyUI and feeding the resulting assets back into ComfyVN Phase 6. It assumes a workstation with GPU acceleration (CUDA 11.8+) and ComfyUI already installed.

1. Prerequisites
----------------
1. Install **ComfyUI Manager** if you have not already:
   ```bash
   cd /path/to/ComfyUI/custom_nodes
   git clone https://github.com/ltdrdata/ComfyUI-Manager.git
   ```
   Launch ComfyUI and open the Manager tab once to complete setup.

2. Install the required audio nodes via Manager (or manually clone into `custom_nodes/`):
   - `ComfyUI-MusicGen` — Meta MusicGen loader/sampler nodes (<https://github.com/cubiq/ComfyUI-Music-Gen>).
   - `ComfyUI-AudioTools` — WAV resampling, loudness normalisation, envelope nodes.
   - Optional: `ComfyUI-UMAPDiffusion` (AudioLDM) for latent audio diffusion alternatives.

3. Download model checkpoints:
   - MusicGen: place `.ckpt` or `.pt` files in `ComfyUI/models/musicgen/`. Recommended: `musicgen-melody`, `musicgen-large`.
   - Reference encoder (if using melody conditioning): e.g. `encodec_32khz` models in `ComfyUI/models/encodec/`.

4. Restart ComfyUI to load the new nodes.

2. Reference Workflow Graph
---------------------------
```
Text Prompt → MusicGen Prompt (node)
Style Controls → MusicGen Conditioning
(Optional) Reference WAV → Encodec Loader ┐
                                        ├→ MusicGen Sampler → Audio Normalise → Audio Save
Seed & CFG Params → MusicGen Sampler ┘
```

- **Text Prompt / Negative Prompt**: Provide lyrical or mood descriptors. Match ComfyVN fields (`scene_id`, `target_style`) for traceability.
- **MusicGen Loader**: Select the desired checkpoint (e.g. `musicgen-melody`) and the target sample rate (32 kHz default). Align `top_k`, `top_p`, `temperature` with your style.
- **MusicGen Sampler**: Set `duration` (target seconds), `cfg_scale` (typically 3.5–7.0), `seed` (pass from ComfyVN cache key), and optionally supply the encoded melody latent.
- **Audio Normalise** (AudioTools): enable loudness target of `-14 LUFS`, apply fade in/out (200 ms) to avoid clicks.
- **Audio Save**: Write to `ComfyUI/output/audio/` using naming convention `scene_{scene_id}_{style}_{seed}.wav`.

3. Parameter Recommendations
----------------------------
| Scenario                | Duration | CFG Scale | Temperature | Notes                                  |
|-------------------------|----------|-----------|-------------|----------------------------------------|
| Lo-fi ambient           | 20 s     | 4.0       | 1.0         | Add tags: “lo-fi, vinyl crackle”       |
| Upbeat battle           | 30 s     | 6.5       | 1.2         | Use `musicgen-large`, top_k=250        |
| Emotional piano         | 25 s     | 3.2       | 0.9         | Use melody conditioning if available   |
| Atmospheric tension     | 45 s     | 5.0       | 1.1         | Layer with AudioTools reverb/filters   |

4. Integrating with ComfyVN
---------------------------
1. Configure ComfyUI to expose an HTTP API (optional but recommended):
   ```bash
   python main.py --listen 0.0.0.0 --port 8188 --enable-cors
   ```
   Use `ComfyUI-Manager` → *Server Tools* → *Enable API Server* if available.

2. Update `comfyvn/config/comfyui.json` (create if missing):
   ```json
   {
     "base_url": "http://127.0.0.1:8188",
     "music_workflow": "workflows/musicgen_remix.json",
     "output_dir": "ComfyUI/output/audio"
   }
   ```

3. Export the ComfyUI workflow graph as `workflows/musicgen_remix.json` and commit to `tools/` or `assets/workflows/`.

4. When the music remix API (`/api/music/remix`) graduates from stub to live execution, the server module should:
   - POST the scene/style/seed metadata to the ComfyUI API, referencing the saved workflow file.
   - Poll for completion and copy the resulting WAV + JSON metadata to `exports/music/`.
   - Update the audio cache using the returned hash to keep deterministic behaviour.

5. Module Installation Checklist
--------------------------------
Run each command from the ComfyUI root directory:
```bash
# ComfyUI Manager (if not present)
git clone https://github.com/ltdrdata/ComfyUI-Manager.git custom_nodes/ComfyUI-Manager

# Music generation nodes
git clone https://github.com/cubiq/ComfyUI-Music-Gen.git custom_nodes/ComfyUI-Music-Gen

# Audio utility nodes
git clone https://github.com/Fannovel16/ComfyUI-Audio-Tools.git custom_nodes/ComfyUI-Audio-Tools

# Optional: AudioLDM diffusion
git clone https://github.com/Kosinkadink/ComfyUI-UMAPDiffusion.git custom_nodes/ComfyUI-UMAPDiffusion
```

After installing, open `ComfyUI-Manager` → *Installed* to verify versions. Update your environment with:
```bash
pip install -r custom_nodes/ComfyUI-Music-Gen/requirements.txt
pip install -r custom_nodes/ComfyUI-Audio-Tools/requirements.txt
```

6. Configuration Tips
---------------------
- Enable `settings → Advanced → Save intermediate audio` in ComfyUI for easier debugging.
- Set `Autosave interval` to 120 s when experimenting with longer renders to avoid data loss.
- For multi-track mixing, chain additional nodes (`AudioTools → Mixer`, `Equaliser`, `Compressor`) before the save step to create layered stems.
- Keep sample rates consistent (32 kHz or 44.1 kHz) so ComfyVN cache keys map cleanly to exported files.
- Document workflow revisions (e.g. `musicgen_remix_v2.json`) and store under version control to maintain provenance.

7. Troubleshooting
------------------
- If MusicGen nodes fail to load, confirm the checkpoint path matches `ComfyUI/models/musicgen/*.ckpt`.
- CUDA out-of-memory: reduce duration, switch to a smaller MusicGen model, or enable `chunk_size=16`.
- Audio pops or clipping: add `AudioTools → Limiter` with ceiling `-1 dB`, fade in/out >150 ms.
- API timeouts: increase ComfyVN `/api/music/remix` timeout to 120 s when running heavy models, and ensure ComfyUI API is accessible.
