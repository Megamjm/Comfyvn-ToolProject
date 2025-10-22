"""
Extractor installer doctor.

Loads the third_party manifest, lists installed tools, and runs lightweight
shim probes so contributors can verify their environment before running the
full extraction wrapper.

Usage:
    python tools/doctor_extractors.py
    python tools/doctor_extractors.py --table
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY_ROOT = ROOT / "third_party"
MANIFEST_PATH = THIRD_PARTY_ROOT / "manifest.json"
SHIM_DIR = THIRD_PARTY_ROOT / "shims"


def load_manifest() -> Dict[str, object]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"format_version": 1, "installed": {}}


def _probe_command(tool_key: str, shim: Path) -> Optional[List[str]]:
    if tool_key in {"rpatool", "unrpa"}:
        return [str(shim), "--help"]
    if tool_key == "arc_unpacker":
        return [str(shim), "--help"]
    if tool_key == "assetstudio":
        return [str(shim), "--help"]
    if tool_key == "garbro":
        return [str(shim), "--help"]
    if tool_key == "krkrextract":
        return [str(shim), "--help"]
    if tool_key == "wolfdec":
        return [str(shim)]
    return None


def _run_probe(command: List[str]) -> Dict[str, object]:
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = "ok" if proc.returncode == 0 else "warn"
        message = (proc.stderr or proc.stdout or "").strip()
        return {
            "status": status,
            "returncode": proc.returncode,
            "message": message[-200:],
        }
    except FileNotFoundError as exc:
        return {"status": "error", "message": str(exc)}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "probe timed out"}
    except Exception as exc:  # pragma: no cover - unexpected platform issues
        return {"status": "error", "message": str(exc)}


def build_report() -> Dict[str, object]:
    manifest = load_manifest()
    installed = manifest.get("installed") or {}
    tools_report: List[Dict[str, object]] = []

    for tool_key, entry in sorted(installed.items()):
        shim_path = SHIM_DIR / tool_key
        shim_exists = shim_path.exists()
        run_info = entry.get("run") or {}
        needs_wine = bool(run_info.get("needs_wine"))
        needs_dotnet = bool(run_info.get("needs_dotnet"))

        probe_status = {
            "status": "skip",
            "message": "Probe not run.",
        }
        command = _probe_command(tool_key, shim_path)
        if command:
            if needs_wine and os.name != "nt" and not shutil.which("wine"):
                probe_status = {
                    "status": "warn",
                    "message": "wine is required for this tool but was not found.",
                }
            elif not shim_exists:
                probe_status = {
                    "status": "error",
                    "message": "Shim is missing.",
                }
            else:
                probe_status = _run_probe(command)

        tools_report.append(
            {
                "key": tool_key,
                "name": entry.get("name"),
                "version": entry.get("version"),
                "license": entry.get("license"),
                "shim": str(shim_path),
                "shim_exists": shim_exists,
                "needs_wine": needs_wine,
                "needs_dotnet": needs_dotnet,
                "probe": probe_status,
            }
        )

    overall_pass = all(
        item["shim_exists"] and item["probe"]["status"] in {"ok", "skip", "warn"}
        for item in tools_report
    )
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest_path": str(MANIFEST_PATH),
        "installed_count": len(installed),
        "tools": tools_report,
        "pass": overall_pass,
    }


def render_table(report: Dict[str, object]) -> str:
    lines = []
    header = f"{'TOOL':12} {'VERSION':10} {'SHIM':40} {'STATUS':8} MESSAGE"
    lines.append(header)
    lines.append("-" * len(header))
    for item in report["tools"]:
        status = item["probe"]["status"]
        message = (item["probe"].get("message") or "").splitlines()
        first_line = message[0] if message else ""
        lines.append(
            f"{item['key']:12} {str(item.get('version') or '-'):10} "
            f"{item['shim'][:40]:40} {status:8} {first_line}"
        )
        for extra in message[1:3]:
            lines.append(f"{'':12} {'':10} {'':40} {'':8} {extra}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extractor doctor.")
    parser.add_argument(
        "--table",
        action="store_true",
        help="Render a text table instead of JSON.",
    )
    args = parser.parse_args(argv)

    report = build_report()
    if args.table:
        print(render_table(report))
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
