"""
One-shot installer for third-party VN extractor utilities.

Usage examples:
    python tools/install_third_party.py --list
    python tools/install_third_party.py --tool arc_unpacker
    python tools/install_third_party.py --all --yes

The script keeps everything under ``third_party/`` and writes shims into
``third_party/shims`` so modders can call extractors without memorising
install paths. Downloads happen only after an explicit acknowledgement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, Optional
from urllib import error, request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY_ROOT = ROOT / "third_party"
SHIM_DIR = THIRD_PARTY_ROOT / "shims"
MANIFEST_PATH = THIRD_PARTY_ROOT / "manifest.json"
DOWNLOAD_DIR = THIRD_PARTY_ROOT / ".downloads"


def _detect_platform() -> tuple[str, str]:
    system = platform.system().lower()
    arch = platform.machine().lower() or "unknown"
    if system.startswith("win"):
        system = "windows"
    elif system.startswith("darwin"):
        system = "darwin"
    elif system.startswith("linux"):
        system = "linux"
    return system, arch


@dataclass
class RunSpec:
    """How to launch a tool once it is unpacked."""

    kind: str  # binary | python-script | python-module
    entry: str
    needs_wine: bool = False
    needs_dotnet: bool = False
    module: Optional[str] = None
    package_hint: Optional[str] = None
    default_args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class ToolVariant:
    """Downloadable artefact for a specific platform."""

    vid: str
    version: str
    url: str
    filename: str
    sha256: str
    size: int
    archive: str  # zip | exe
    supported_platforms: List[str]
    run: RunSpec
    notes: str = ""


@dataclass
class ThirdPartyTool:
    key: str
    display_name: str
    homepage: str
    license: str
    license_url: str
    warning: str
    description: str
    aliases: List[str]
    variants: List[ToolVariant]

    def match(self, name: str) -> bool:
        name = name.lower()
        return name == self.key or name in self.aliases

    def choose_variant(self, platform_key: str) -> ToolVariant:
        candidates = [
            variant
            for variant in self.variants
            if platform_key in variant.supported_platforms
        ]
        if not candidates:
            raise KeyError(
                f"No variant for tool '{self.key}' on platform '{platform_key}'"
            )
        # prefer most specific (not strictly necessary with current data)
        return candidates[0]


TOOLS: Dict[str, ThirdPartyTool] = {}


def _register(tool: ThirdPartyTool) -> None:
    TOOLS[tool.key] = tool


def _init_tool_catalog() -> None:
    """Populate the in-memory tool catalog."""
    _register(
        ThirdPartyTool(
            key="garbro",
            display_name="GARbro",
            homepage="https://github.com/morkt/GARbro",
            license="MIT",
            license_url="https://github.com/morkt/GARbro/blob/master/LICENSE",
            warning=(
                "GARbro can unpack commercial archives. Use only with games you own "
                "and verify redistribution rights before exporting assets."
            ),
            description=(
                "GUI/CLI extractor with broad engine support (KiriKiri, CatSystem2, etc.). "
                "This installer ships the 1.4.32 portable build for repeatable hashes."
            ),
            aliases=["garbro-cli", "gar"],
            variants=[
                ToolVariant(
                    vid="win-portable-1.4.32",
                    version="1.4.32",
                    url="https://github.com/morkt/GARbro/releases/download/v1.4.32/GARbro-v1.4.32.zip",
                    filename="GARbro-v1.4.32.zip",
                    sha256="1c24855443411e0d4d9b2eb379d446aafd5e914c7b4a8c0c3983d6590bc8e381",
                    size=9849173,
                    archive="zip",
                    supported_platforms=["windows", "linux", "darwin"],
                    run=RunSpec(
                        kind="binary",
                        entry="GARbro.GUI.exe",
                        needs_wine=True,
                    ),
                    notes=(
                        "Newer releases are distributed as .rar installers. "
                        "This portable zip still exposes command arguments via GARbro.GUI.exe."
                    ),
                )
            ],
        )
    )
    _register(
        ThirdPartyTool(
            key="arc_unpacker",
            display_name="arc_unpacker",
            homepage="https://github.com/vn-tools/arc_unpacker",
            license="MIT",
            license_url="https://github.com/vn-tools/arc_unpacker/blob/master/docs/license.md",
            warning=(
                "Reverse engineering of archives may be restricted in your jurisdiction. "
                "Ensure you have legal rights before proceeding."
            ),
            description="Popular command-line extractor for many VN archives (arc/xp3/dat/pak/etc.).",
            aliases=["arc", "arc-unpack"],
            variants=[
                ToolVariant(
                    vid="win-bin-0.11",
                    version="0.11",
                    url="https://github.com/vn-tools/arc_unpacker/releases/download/0.11/arc_unpacker-0.11-bin.zip",
                    filename="arc_unpacker-0.11-bin.zip",
                    sha256="c55bdd25a8f4e0f9aa58e2f2c806faf179514f4b929c43016dbf606d16ba2bc7",
                    size=2851020,
                    archive="zip",
                    supported_platforms=["windows", "linux", "darwin"],
                    run=RunSpec(
                        kind="binary",
                        entry="arc_unpacker.exe",
                        needs_wine=True,
                    ),
                )
            ],
        )
    )
    _register(
        ThirdPartyTool(
            key="rpatool",
            display_name="rpatool",
            homepage="https://github.com/Shizmob/rpatool",
            license="MIT",
            license_url="https://github.com/Shizmob/rpatool/blob/master/LICENSE",
            warning="Ren'Py archives (.rpa) may contain copyrighted content. Extract only what you own.",
            description="Python script for unpacking Ren'Py .rpa archives (supports RPA-2.0/3.0/4.0).",
            aliases=["rpa"],
            variants=[
                ToolVariant(
                    vid="py-commit-74f26d5",
                    version="2022-08-23",
                    url="https://github.com/Shizmob/rpatool/archive/74f26d5dfdd645483e02552aa766ca447ad6b191.zip",
                    filename="rpatool-74f26d5.zip",
                    sha256="364a34cbedbe67d815cd17ae160d82d0ad7c55241a8097b75da577694e8549cd",
                    size=7968,
                    archive="zip",
                    supported_platforms=["windows", "linux", "darwin"],
                    run=RunSpec(
                        kind="python-script",
                        entry="rpatool",
                    ),
                )
            ],
        )
    )
    _register(
        ThirdPartyTool(
            key="unrpa",
            display_name="unrpa",
            homepage="https://github.com/lattyware/unrpa",
            license="MIT",
            license_url="https://github.com/Lattyware/unrpa/blob/master/COPYING",
            warning="Use only on Ren'Py titles you have explicit rights to mod or archive.",
            description="Pure-Python Ren'Py extractor with support for modern RPA formats.",
            aliases=["un-rpa"],
            variants=[
                ToolVariant(
                    vid="py-tag-2.3.0",
                    version="2.3.0",
                    url="https://github.com/Lattyware/unrpa/archive/refs/tags/2.3.0.zip",
                    filename="unrpa-2.3.0.zip",
                    sha256="b01041148dab480dd2be907f2ffef954352e5feaf5f2547b42035c1d9f74af59",
                    size=30061,
                    archive="zip",
                    supported_platforms=["windows", "linux", "darwin"],
                    run=RunSpec(
                        kind="python-module",
                        entry="unrpa",
                        module="unrpa",
                        package_hint="unrpa",
                    ),
                )
            ],
        )
    )
    _register(
        ThirdPartyTool(
            key="krkrextract",
            display_name="KrkrExtract",
            homepage="https://github.com/xmoezzz/KrkrExtract",
            license="GPL-3.0-or-later",
            license_url="https://github.com/xmoezzz/KrkrExtract/blob/master/LICENSE",
            warning="KrkrExtract targets KiriKiri XP3 titles. Some EULAs forbid unpacking; review before use.",
            description="Community-maintained XP3 extractor with conversion helpers for KiriKiri engines.",
            aliases=["krkr", "xp3"],
            variants=[
                ToolVariant(
                    vid="win-lite-5.0.0.2",
                    version="5.0.0.2",
                    url="https://github.com/xmoezzz/KrkrExtract/releases/download/5.0.0.2/KrkrExtract.Lite.exe",
                    filename="KrkrExtract.Lite.exe",
                    sha256="eb5d609b1dcd6ab9c163c3640c06ff1cd80875592221e4d1208beb318c69ce89",
                    size=534016,
                    archive="exe",
                    supported_platforms=["windows", "linux"],
                    run=RunSpec(
                        kind="binary",
                        entry="KrkrExtract.Lite.exe",
                        needs_wine=True,
                    ),
                    notes="Lite build ships as a standalone executable.",
                )
            ],
        )
    )
    _register(
        ThirdPartyTool(
            key="assetstudio",
            display_name="AssetStudio",
            homepage="https://github.com/Perfare/AssetStudio",
            license="MIT",
            license_url="https://github.com/Perfare/AssetStudio/blob/master/LICENSE",
            warning="Unity asset bundles may contain licensed content. Confirm redistribution rights.",
            description="Unity asset viewer/extractor (headless export supported via CLI arguments).",
            aliases=["asset-studio", "unity"],
            variants=[
                ToolVariant(
                    vid="win-net6-0.16.47",
                    version="0.16.47",
                    url="https://github.com/Perfare/AssetStudio/releases/download/v0.16.47/AssetStudio.net6.v0.16.47.zip",
                    filename="AssetStudio.net6.v0.16.47.zip",
                    sha256="af600c5c0b48648b878ba5eb43dcaf74dcf021fa31de8718fdcd90adb960d7dd",
                    size=10733396,
                    archive="zip",
                    supported_platforms=["windows", "linux"],
                    run=RunSpec(
                        kind="binary",
                        entry="AssetStudioGUI.exe",
                        needs_wine=True,
                    ),
                    notes="Use the --export command-line options for unattended exports.",
                )
            ],
        )
    )
    _register(
        ThirdPartyTool(
            key="wolfdec",
            display_name="WolfDec",
            homepage="https://github.com/Sinflower/WolfDec",
            license="MIT",
            license_url="https://github.com/Sinflower/WolfDec/blob/master/LICENSE",
            warning="Wolf RPG titles often forbid redistribution of extracted data. Respect the originating license.",
            description="Wolf RPG archive extractor / decoder.",
            aliases=["wolf-dec", "wolf"],
            variants=[
                ToolVariant(
                    vid="win-exe-0.3.3",
                    version="0.3.3",
                    url="https://github.com/Sinflower/WolfDec/releases/download/v0.3.3/WolfDec.exe",
                    filename="WolfDec.exe",
                    sha256="b6c85fd2565eb18990ab8b5007a70310582f248eb500dddd0be096cb23a5604d",
                    size=263680,
                    archive="exe",
                    supported_platforms=["windows", "linux"],
                    run=RunSpec(
                        kind="binary",
                        entry="WolfDec.exe",
                        needs_wine=True,
                    ),
                )
            ],
        )
    )


_init_tool_catalog()


def _load_manifest() -> Dict[str, object]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"format_version": 1, "installed": {}}


def _save_manifest(manifest: Dict[str, object]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = request.Request(url, method="GET")
    with request.urlopen(req) as resp, dest.open("wb") as fh:
        chunk = resp.read(1024 * 16)
        while chunk:
            fh.write(chunk)
            chunk = resp.read(1024 * 16)


def _verify_download(path: Path, sha256: str, size: int) -> None:
    actual_size = path.stat().st_size
    if size and actual_size != size:
        raise RuntimeError(
            f"Size mismatch for {path.name} (expected {size}, got {actual_size})"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        raise RuntimeError(
            f"Checksum mismatch for {path.name} (expected {sha256}, got {digest})"
        )


def _extract_zip(archive_path: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path) as zip_file:
        zip_file.extractall(target_dir)


def _find_file(root: Path, filename: str) -> Optional[Path]:
    for candidate in root.rglob(filename):
        if candidate.is_file():
            return candidate
    return None


def _find_module_root(root: Path, module_name: str) -> Optional[Path]:
    for init_file in root.rglob("__init__.py"):
        if init_file.parent.name == module_name:
            return init_file.parent.parent
    return None


def _format_warning(tool: ThirdPartyTool) -> str:
    return textwrap.dedent(
        f"""
        ── {tool.display_name} ({tool.homepage})
           License: {tool.license}
           Warning: {tool.warning}
        """
    ).strip()


def _acknowledge(tools: Iterable[ThirdPartyTool], assume_yes: bool) -> None:
    if assume_yes:
        return
    print("Third-party extractor installation requires an explicit acknowledgement.")
    print()
    for tool in tools:
        print(_format_warning(tool))
    print()
    prompt = "Type 'agree' to continue: "
    response = input(prompt).strip().lower()
    if response != "agree":
        raise SystemExit("Aborted — acknowledgement missing.")


def _platform_summary() -> str:
    system, arch = _detect_platform()
    return f"{system}/{arch}"


def _render_tool(tool: ThirdPartyTool) -> Dict[str, object]:
    return {
        "key": tool.key,
        "name": tool.display_name,
        "license": tool.license,
        "homepage": tool.homepage,
        "description": tool.description,
        "warning": tool.warning,
        "variants": [
            {
                "id": variant.vid,
                "version": variant.version,
                "platforms": variant.supported_platforms,
                "archive": variant.archive,
                "url": variant.url,
                "hash": variant.sha256,
                "size": variant.size,
                "notes": variant.notes,
            }
            for variant in tool.variants
        ],
    }


def _manifest_entry(
    tool: ThirdPartyTool,
    variant: ToolVariant,
    run_data: Dict[str, str],
    install_dir: Path,
    archive_path: Path,
    entry_path: Path,
) -> Dict[str, object]:
    return {
        "key": tool.key,
        "name": tool.display_name,
        "version": variant.version,
        "variant": variant.vid,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "download": {
            "url": variant.url,
            "filename": variant.filename,
            "sha256": variant.sha256,
            "size": variant.size,
            "archive": variant.archive,
        },
        "paths": {
            "install_dir": str(install_dir),
            "archive": str(archive_path),
            "entry": str(entry_path),
        },
        "run": run_data,
        "license": {
            "name": tool.license,
            "url": tool.license_url,
        },
        "notes": variant.notes,
    }


def _build_run_data(
    run_spec: RunSpec,
    entry_path: Path,
    install_dir: Path,
) -> Dict[str, object]:
    run_data: Dict[str, object] = {
        "kind": run_spec.kind,
        "needs_wine": bool(run_spec.needs_wine),
        "needs_dotnet": bool(run_spec.needs_dotnet),
        "default_args": run_spec.default_args,
        "env": run_spec.env,
    }
    if run_spec.kind == "python-module":
        module_root = _find_module_root(
            install_dir, run_spec.package_hint or run_spec.entry
        )
        if not module_root:
            raise RuntimeError(f"Unable to locate python module '{run_spec.entry}'")
        run_data["module"] = run_spec.module or run_spec.entry
        run_data["package_path"] = str(module_root)
        run_data["entry_path"] = str(module_root)
        run_data["working_dir"] = str(module_root)
    else:
        run_data["entry_path"] = str(entry_path)
        run_data["working_dir"] = str(entry_path.parent)
    return run_data


def _create_shim(tool_key: str) -> None:
    template = Template(
        """\
        #!/usr/bin/env python3
        \"\"\"Auto-generated shim for $tool.\"\"\"
        import json
        import os
        import pathlib
        import shutil
        import subprocess
        import sys

        MANIFEST = pathlib.Path(__file__).resolve().parents[1] / "manifest.json"
        TOOL = "$tool"


        def _load():
            try:
                data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - shim runtime only
                print("[shim:" + TOOL + "] failed to read manifest: {}".format(exc), file=sys.stderr)
                sys.exit(2)
            info = (data.get("installed") or {}).get("$tool")
            if not info:
                print(
                    "[shim:" + TOOL + "] tool not installed. Run tools/install_third_party.py first.",
                    file=sys.stderr,
                )
                sys.exit(2)
            return info


        def _python_path(env, package_path):
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                package_path
                if not existing
                else package_path + os.pathsep + existing
            )


        def main(argv: list[str]) -> int:
            info = _load()
            run = info["run"]
            env = os.environ.copy()
            env.update(run.get("env") or {})
            entry = pathlib.Path(run["entry_path"]).resolve()
            if run["kind"] == "python-script":
                cmd = [sys.executable, str(entry)]
            elif run["kind"] == "python-module":
                module = run.get("module") or TOOL
                if run.get("package_path"):
                    _python_path(env, run["package_path"])
                cmd = [sys.executable, "-m", module]
            else:
                cmd = [str(entry)]

            if run.get("needs_wine") and os.name != "nt":
                wine = shutil.which("wine")
                if not wine:
                    print(
                        "[shim:" + TOOL + "] wine is required but was not found in PATH.",
                        file=sys.stderr,
                    )
                    return 2
                cmd = [wine, str(entry)]

            if run.get("needs_dotnet") and os.name != "nt":
                dotnet = shutil.which("dotnet")
                if not dotnet:
                    print(
                        "[shim:" + TOOL + "] dotnet runtime required but missing.",
                        file=sys.stderr,
                    )
                    return 2
                cmd = [dotnet, str(entry)]

            cmd.extend(run.get("default_args") or [])
            cmd.extend(argv[1:])

            cwd = run.get("working_dir")
            return subprocess.call(cmd, env=env, cwd=cwd or entry.parent)


        if __name__ == "__main__":
            sys.exit(main(sys.argv))
        """
    )
    shim_template = textwrap.dedent(template.substitute(tool=tool_key))

    SHIM_DIR.mkdir(parents=True, exist_ok=True)
    shim_path = SHIM_DIR / tool_key
    shim_path.write_text(shim_template, encoding="utf-8")
    shim_path.chmod(0o755)
    # Windows convenience launcher (.cmd)
    cmd_path = SHIM_DIR / f"{tool_key}.cmd"
    cmd_path.write_text(
        f'@echo off\r\npython "%~dp0{tool_key}" %*\r\n', encoding="utf-8"
    )


def install_tool(tool_name: str, assume_yes: bool = False) -> None:
    system, _arch = _detect_platform()
    tool = None
    for candidate in TOOLS.values():
        if candidate.match(tool_name):
            tool = candidate
            break
    if not tool:
        raise KeyError(f"Unknown tool '{tool_name}'. Run with --list to see options.")

    manifest = _load_manifest()
    installed = manifest.get("installed", {})
    existing = installed.get(tool.key)

    variant = tool.choose_variant(system)
    install_dir = THIRD_PARTY_ROOT / tool.key / variant.version
    archive_dest = DOWNLOAD_DIR / variant.filename

    if (
        existing
        and existing.get("version") == variant.version
        and existing.get("download", {}).get("sha256") == variant.sha256
        and Path(existing.get("run", {}).get("entry_path", "")).exists()
    ):
        _create_shim(tool.key)
        print(f"[ok] {tool.display_name} already installed ({variant.version}).")
        return

    _acknowledge([tool], assume_yes=assume_yes)

    print(f"[fetch] Downloading {tool.display_name} ({variant.version})...")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _download(variant.url, archive_dest)
    except error.URLError as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc

    try:
        _verify_download(archive_dest, variant.sha256, variant.size)
    except Exception:
        archive_dest.unlink(missing_ok=True)
        raise

    if variant.archive == "zip":
        _extract_zip(archive_dest, install_dir)
    else:
        install_dir.mkdir(parents=True, exist_ok=True)
        target_file = install_dir / variant.filename
        shutil.copy2(archive_dest, target_file)

    if variant.run.kind == "binary":
        entry = _find_file(install_dir, variant.run.entry)
        if not entry:
            raise RuntimeError(f"Unable to locate executable '{variant.run.entry}'")
    elif variant.run.kind == "python-script":
        entry = _find_file(install_dir, variant.run.entry)
        if not entry:
            raise RuntimeError(f"Unable to locate python script '{variant.run.entry}'")
    elif variant.run.kind == "python-module":
        entry = install_dir / variant.run.entry
    else:
        raise RuntimeError(f"Unsupported run kind '{variant.run.kind}'")

    run_info = _build_run_data(variant.run, entry, install_dir)
    manifest_entry = _manifest_entry(
        tool=tool,
        variant=variant,
        run_data=run_info,
        install_dir=install_dir,
        archive_path=archive_dest,
        entry_path=entry if entry.exists() else install_dir,
    )
    manifest["installed"][tool.key] = manifest_entry
    _save_manifest(manifest)
    _create_shim(tool.key)
    print(f"[ok] Installed {tool.display_name} → {install_dir}")

    if run_info.get("needs_wine") and system != "windows":
        if not shutil.which("wine"):
            print(
                "[warn] wine was not detected. Install wine to run Windows binaries.",
                file=sys.stderr,
            )


def list_tools() -> None:
    payload = {
        "platform": _platform_summary(),
        "tools": [_render_tool(tool) for tool in TOOLS.values()],
    }
    print(json.dumps(payload, indent=2))


def show_info(tool_name: str) -> None:
    for tool in TOOLS.values():
        if tool.match(tool_name):
            print(json.dumps(_render_tool(tool), indent=2))
            return
    raise KeyError(f"Unknown tool '{tool_name}'")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install third-party VN extractors.")
    parser.add_argument("--tool", action="append", dest="tools")
    parser.add_argument(
        "--all", action="store_true", help="Install every supported tool."
    )
    parser.add_argument(
        "--list", action="store_true", help="List catalog in JSON format."
    )
    parser.add_argument("--info", help="Show catalog metadata for a specific tool.")
    parser.add_argument(
        "--yes", action="store_true", help="Skip acknowledgement prompt."
    )
    args = parser.parse_args(argv)

    THIRD_PARTY_ROOT.mkdir(exist_ok=True)

    if args.list:
        list_tools()
        return 0
    if args.info:
        try:
            show_info(args.info)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    targets: List[str] = []
    if args.all:
        targets.extend(sorted(TOOLS.keys()))
    if args.tools:
        targets.extend(args.tools)
    if not targets:
        parser.error("Specify --tool <name> or --all (try --list to inspect catalog).")

    exit_code = 0
    for name in targets:
        try:
            install_tool(name, assume_yes=args.yes)
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
