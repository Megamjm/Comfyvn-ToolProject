# Phase 2/2 Project Integration Chat — System Checker
# Usage:
#   python tools/check_current_system.py --profile p1_worldlines --base http://127.0.0.1:8001
#   python tools/check_current_system.py --profile p1_extractors

import argparse
import json
import os
import pathlib
import sys
import time
from urllib import error, request

DEF_CONF = "tools/check_profiles.json"
DEF_FLAGS = "config/comfyvn.json"


def _http_get(url: str, timeout=3.0):
    try:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except error.HTTPError as e:
        return e.code, b""
    except Exception:
        return None, b""


def _http_options(url: str, timeout=3.0):
    try:
        req = request.Request(url, method="OPTIONS")
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.headers.get("Allow", "")
    except Exception:
        return None, ""


def load_json(path):
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser(
        description="Check how current systems work (flags, routes, files)."
    )
    ap.add_argument(
        "--profile", required=True, help="Profile key in tools/check_profiles.json"
    )
    ap.add_argument("--conf", default=DEF_CONF)
    ap.add_argument("--flags-file", default=DEF_FLAGS)
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    args = ap.parse_args()

    profiles = load_json(args.conf)
    profile = profiles.get(args.profile, {})
    out = {
        "ts": time.time(),
        "profile": args.profile,
        "base": args.base,
        "pass": True,
        "flags": [],
        "routes": [],
        "files": [],
        "notes": [],
    }

    # Flags
    flags = load_json(args.flags_file)
    feature_flags = (flags.get("features") or {}) if flags else {}
    for f in profile.get("flags", []):
        key = f.get("key")
        expect = f.get("expect", False)
        required = bool(f.get("required", True))
        got = bool(feature_flags.get(key, None))
        ok = (got == expect) if required else True  # if optional, don't fail
        out["flags"].append(
            {"key": key, "expect": expect, "got": got, "ok": ok, "required": required}
        )
        if required and not ok:
            out["pass"] = False

    # Routes
    base = args.base.rstrip("/")
    for r in profile.get("routes", []):
        path = r.get("path")
        method = (r.get("method") or "GET").upper()
        required = bool(r.get("required", True))
        status, extra = (None, "")
        if method == "GET":
            code, _ = _http_get(f"{base}{path}")
            status = code
        else:
            code, allow = _http_options(f"{base}{path}")
            status = code
            extra = allow
        ok = status is not None and status >= 200 and status < 500
        out["routes"].append(
            {
                "path": path,
                "method": method,
                "status": status,
                "allow": extra,
                "ok": ok,
                "required": required,
            }
        )
        if required and not ok:
            out["pass"] = False

    # Files
    for f in profile.get("files", []):
        path = f.get("path")
        required = bool(f.get("required", True))
        exists = os.path.exists(path)
        out["files"].append(
            {
                "path": path,
                "exists": exists,
                "required": required,
                "ok": (exists or not required),
            }
        )
        if required and not exists:
            out["pass"] = False

    print(json.dumps(out, indent=2))
    sys.exit(0 if out["pass"] else 2)


if __name__ == "__main__":
    main()
