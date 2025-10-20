"""
Download helper for user-supplied extractor binaries (arc_unpacker, rpatool…).

We never bundle third-party tools; instead, we fetch them on demand after the
user explicitly acknowledges licensing/legality warnings. Downloads default to
``tools/extractors/<name>/`` and callers should register the resulting binary
with :mod:`comfyvn.server.core.external_extractors`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import httpx

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractorMeta:
    name: str
    url: str
    filename: str
    extensions: list[str]
    warning: str
    license: str
    notes: str


KNOWN_EXTRACTORS: Dict[str, ExtractorMeta] = {
    "arc_unpacker": ExtractorMeta(
        name="arc_unpacker",
        url="https://github.com/vn-tools/arc_unpacker/releases/latest/download/arc_unpacker.exe",
        filename="arc_unpacker.exe",
        extensions=[".arc", ".xp3", ".dat", ".vfs", ".pak"],
        warning="Use only with archives you have rights to unpack. Some jurisdictions restrict reverse engineering.",
        license="MIT",
        notes="Multi-engine archive extractor popular in VN communities.",
    ),
    "rpatool": ExtractorMeta(
        name="rpatool",
        url="https://github.com/shizmob/rpatool/archive/refs/heads/master.zip",
        filename="rpatool-master.zip",
        extensions=[".rpa"],
        warning="Ren'Py .rpa archives may contain copyrighted material; unpack only when legally permitted.",
        license="MIT",
        notes="Python-based Ren'Py archive helper (requires local Python to run).",
    ),
    "unrpa": ExtractorMeta(
        name="unrpa",
        url="https://github.com/Lattyware/unrpa/archive/refs/heads/master.zip",
        filename="unrpa-master.zip",
        extensions=[".rpa"],
        warning="Ren'Py .rpa archives may contain copyrighted material; unpack only when legally permitted.",
        license="MIT",
        notes="Fallback Ren'Py extractor (pure Python script).",
    ),
    "lightvntools_github": ExtractorMeta(
        name="Light.vnTools (GitHub mirror)",
        url="https://github.com/bungaku-moe/Light.vnTools/archive/refs/heads/main.zip",
        filename="Light.vnTools-main.zip",
        extensions=[".xp3", ".ypf", ".vfs", ".arc"],
        warning="Light.vnTools may include unpackers for copyrighted games. Confirm you own the content before extracting.",
        license="GPL-3.0-or-later",
        notes="Command-line utilities for common VN archives (requires extraction of the downloaded zip).",
    ),
    "lightvntools_gitlab": ExtractorMeta(
        name="Light.vnTools (GitLab upstream)",
        url="https://gitlab.com/kiraio-moe/Light-vnTools/-/archive/main/Light-vnTools-main.zip",
        filename="Light-vnTools-main.zip",
        extensions=[".xp3", ".ypf", ".vfs", ".arc"],
        warning="Light.vnTools may include unpackers for copyrighted games. Confirm you own the content before extracting.",
        license="GPL-3.0-or-later",
        notes="Original upstream repository. Extract zip and build/run according to the included README.",
    ),
    "garbro_cli": ExtractorMeta(
        name="GARbro (CLI mode)",
        url="https://github.com/morkt/GARbro/releases/latest/download/GARbro.zip",
        filename="GARbro.zip",
        extensions=[".arc", ".xp3", ".int", ".dat", ".hg2", ".hg3", ".pac"],
        warning="GARbro supports many commercial archives; ensure you have redistribution rights before extracting.",
        license="MIT",
        notes="Windows GUI + CLI utility. After download, extract and use GARbro.CommandLine.exe for batch extraction.",
    ),
    "krkrextract": ExtractorMeta(
        name="KrkrExtract",
        url="https://github.com/xmoeproject/KrkrExtract/archive/refs/heads/master.zip",
        filename="KrkrExtract-master.zip",
        extensions=[".xp3", ".tlg"],
        warning="KrkrExtract targets KiriKiri engines. Some titles forbid re-distribution; review the EULA.",
        license="GPL-3.0-or-later",
        notes="Requires Visual Studio build; includes tlg conversion helpers.",
    ),
    "xp3tools": ExtractorMeta(
        name="xp3tools",
        url="https://github.com/uyjulian/xp3tools/archive/refs/heads/master.zip",
        filename="xp3tools-master.zip",
        extensions=[".xp3"],
        warning="XP3 archives may contain licensed content; extract only what you own.",
        license="MIT",
        notes="Python-based XP3 extractor and repacker scripts.",
    ),
    "nsadec": ExtractorMeta(
        name="nsadec",
        url="https://github.com/xtokio/nsadec/archive/refs/heads/master.zip",
        filename="nsadec-master.zip",
        extensions=[".nsa", ".ns2", ".sar"],
        warning="NScripter archives may embed licensed content. Extract only when permitted.",
        license="GPL-2.0-or-later",
        notes="C++ NSA/NS2 decompressor; build from source, then run the generated binary.",
    ),
    "siglusextract": ExtractorMeta(
        name="SiglusExtract",
        url="https://github.com/xmoeproject/SiglusExtract/archive/refs/heads/master.zip",
        filename="SiglusExtract-master.zip",
        extensions=[".pck", ".ss", ".bin"],
        warning="Siglus engine assets are typically proprietary; verify your rights before use.",
        license="GPL-3.0-or-later",
        notes="Extracts SiglusEngine archives (Key/VisualArt's titles). Requires build from source.",
    ),
    "ypf_unpacker": ExtractorMeta(
        name="YPF Unpacker",
        url="https://github.com/wetor/LibYPF/archive/refs/heads/master.zip",
        filename="LibYPF-master.zip",
        extensions=[".ypf"],
        warning="Yu-RIS archives may contain licensed content; confirm usage rights.",
        license="MIT",
        notes="C# library + tool for Yu-RIS *.ypf archives.",
    ),
    "catsystem2_tools": ExtractorMeta(
        name="CatSystem2 Tools",
        url="https://github.com/arcusmaximus/CatSystem2Tools/archive/refs/heads/master.zip",
        filename="CatSystem2Tools-master.zip",
        extensions=[".int", ".dat", ".cst", ".fes"],
        warning="CatSystem2 data often includes copyrighted assets; extract responsibly.",
        license="MIT",
        notes="Includes converters for CatSystem2 archives and script formats.",
    ),
    "hg2_converter": ExtractorMeta(
        name="HG2 to PNG Converter",
        url="https://github.com/arcusmaximus/hg2tojpg/archive/refs/heads/master.zip",
        filename="hg2tojpg-master.zip",
        extensions=[".hg2", ".hg3"],
        warning="Image assets may be copyrighted; ensure you have conversion rights.",
        license="GPL-3.0-or-later",
        notes="Command-line converter for CatSystem2 HG2/HG3 images.",
    ),
    "bgi_tools": ExtractorMeta(
        name="BGI Tools",
        url="https://github.com/arcusmaximus/BGI-tools/archive/refs/heads/master.zip",
        filename="BGI-tools-master.zip",
        extensions=[".arc", ".org", ".ke"],
        warning="BGI/Ethornell assets are proprietary; extract only with permission.",
        license="GPL-3.0-or-later",
        notes="Tools for Buriko General Interpreter archives and scripts.",
    ),
    "unity_asset_ripper": ExtractorMeta(
        name="AssetRipper",
        url="https://github.com/AssetRipper/AssetRipper/releases/latest/download/AssetRipper_win64.zip",
        filename="AssetRipper_win64.zip",
        extensions=[".assets", ".bundle", ".unity3d"],
        warning="Unity AssetBundles may contain licensed content; ensure compliance with the game's EULA.",
        license="MIT",
        notes="GUI/CLI utility for Unity asset extraction; includes executable in the release zip.",
    ),
    "assetstudio_cli": ExtractorMeta(
        name="AssetStudio",
        url="https://github.com/Perfare/AssetStudio/releases/latest/download/AssetStudio.zip",
        filename="AssetStudio.zip",
        extensions=[".assets", ".bundle"],
        warning="Unity assets might be protected content; verify rights before extraction.",
        license="MIT",
        notes="Popular Unity asset viewer/extractor (GUI + command-line).",
    ),
    "livemaker_unpacker": ExtractorMeta(
        name="LiveMaker Unpacker",
        url="https://github.com/ZXB0T/LiveMaker-Extractor/archive/refs/heads/master.zip",
        filename="LiveMaker-Extractor-master.zip",
        extensions=[".paz", ".lmd"],
        warning="LiveMaker archives can hold commercial assets; extract only if authorized.",
        license="MIT",
        notes="Community-maintained extractor for LiveMaker archives.",
    ),
    "tyrano_parser": ExtractorMeta(
        name="TyranoParser",
        url="https://github.com/hebiiro/TyranoScriptTools/archive/refs/heads/master.zip",
        filename="TyranoScriptTools-master.zip",
        extensions=[".ks", ".tb"],  # Tyrano scenario/assets
        warning="Tyrano projects may include licensed art/audio; confirm rights before repacking.",
        license="MIT",
        notes="Python utilities for TyranoScript scenario parsing and asset extraction.",
    ),
    "krgem_unpacker": ExtractorMeta(
        name="KrKrZ/EM Extractor",
        url="https://github.com/BelgianChocolate/KirikiriZTools/archive/refs/heads/master.zip",
        filename="KirikiriZTools-master.zip",
        extensions=[".xp3", ".tlg", ".ks"],
        warning="KrKrZ archives usually contain licensed content; extract only what you own.",
        license="MIT",
        notes="Updated Kirikiri Z extractor with patch generation support.",
    ),
    "reallive_tools": ExtractorMeta(
        name="RLDev Tools",
        url="https://github.com/Noisy-Flake/rl-devtools/archive/refs/heads/master.zip",
        filename="rl-devtools-master.zip",
        extensions=[".org", ".utf", ".pck"],
        warning="RealLive assets may be copyrighted; use only for legitimate modding/backups.",
        license="GPL-2.0-or-later",
        notes="Old but still useful toolset for RealLive script/assets (requires build).",
    ),
}


def _download_to_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Downloading extractor %s -> %s", url, dest)
    try:
        with httpx.stream("GET", url, timeout=60.0) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
    except Exception as exc:  # pragma: no cover - network dependent
        LOGGER.error("Failed to download %s: %s", url, exc)
        raise RuntimeError(f"download failed: {exc}") from exc


def install_extractor(
    name: str,
    *,
    target_dir: Path | str | None = None,
    download_func=None,
) -> Dict[str, str]:
    """Download a known extractor into ``target_dir`` (default tools/extractors)."""
    name_key = name.lower().strip()
    meta = KNOWN_EXTRACTORS.get(name_key)
    if not meta:
        raise KeyError(f"unknown extractor '{name}'")

    target = Path(target_dir or ("tools/extractors/" + name_key)).resolve()
    target.mkdir(parents=True, exist_ok=True)
    dest = target / meta.filename

    if download_func is None:
        download_func = _download_to_file
    download_func(meta.url, dest)

    os.chmod(dest, 0o755)
    LOGGER.info("Extractor %s installed to %s", name_key, dest)
    return {
        "name": meta.name,
        "path": str(dest),
        "warning": meta.warning,
        "license": meta.license,
        "notes": meta.notes,
        "extensions": meta.extensions,
    }


__all__ = ["KNOWN_EXTRACTORS", "install_extractor", "ExtractorMeta"]
