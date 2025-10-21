# Packaging Plan (Draft)

This document captures the initial packaging strategy for ComfyVN Studio following the Phase 4 runtime/path updates.

## Goals

1. Provide reproducible builds for the primary platforms (Windows, macOS, Linux).
2. Keep the Python wheel as the canonical distribution for power users and automated deployments.
3. Ship self-contained binaries (PyInstaller / AppImage / notarised `.app`) for non-technical artists.
4. Ensure the packaging pipeline respects the new platform-specific runtime directories and symlink shims.

## Artifacts

| Artifact | Target | Notes |
| --- | --- | --- |
| `comfyvn-studio-x.y.z-py3-none-any.whl` | PyPI / internal index | Base distribution with optional extras for GUI + server. |
| `ComfyVN-Studio-x.y.z-win64.exe` | Windows 10+ | PyInstaller one-dir build, bundles Python, sets `%LOCALAPPDATA%/ComfyVN Studio` runtime roots. |
| `ComfyVN-Studio-x.y.z.dmg` | macOS 13+ | Universal2 build, notarised; installs into `/Applications`, runtime dirs under `~/Library/Application Support/ComfyVN Studio`. |
| `ComfyVN-Studio-x.y.z.AppImage` | Linux x86_64 | Uses `appimage-builder`; embeds Qt libs and honours XDG base directories. |

## Build pipeline sketch

1. **Pre-flight**
   - `pip install -r requirements.txt` (plus platform extras).
   - Run `python -m compileall comfyvn extensions tools` to catch syntax errors.
   - Execute `pytest` (or targeted smoke tests) before every packaging step.

2. **Wheel**
   - `python -m build --wheel` with `pyproject.toml` metadata.
   - Upload to internal index for QA.

3. **Windows**
   - PyInstaller spec file (`packaging/windows/comfyvn.spec`) ensures `platformdirs` + Qt plugins are included.
   - Post-build script writes `runtime_paths.ensure_portable_symlinks()` on first launch.
   - Sign executable with organisation certificate.

4. **macOS**
   - Use `briefcase` or `pyinstaller` with universal2 Python.
   - Bundle `PySide6`, add `Info.plist` entries for sandbox exceptions.
   - Codesign + notarise via `xcrun notarytool`.

5. **Linux AppImage**
   - Base on manylinux wheel + runtime dependencies (Qt, SSL).
   - Embed launcher script that sets `COMFYVN_RUNTIME_ROOT=${APPDIR}/userdata` when running in portable mode.

6. **Artifacts**
   - Publish to GitHub Releases (or internal equivalent) with checksums and CHANGELOG excerpt.

## Open tasks

- [ ] Write PyInstaller spec templates for Windows/macOS.
- [ ] Create Docker-based builder for the AppImage artefact.
- [ ] Automate runtime smoke tests post-build (`smoke_checks.py`, GUI launch, warning bus sanity check).
- [ ] Document the release checklist in `docs/release_checklist.md` (pending).
- [ ] Integrate signing credentials into CI (GitHub Actions/ADO) with minimal surface area.
