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

from comfyvn.config import ports as ports_config

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


def _compose_base(host: str, port: str) -> str:
    host = (host or "").strip()
    port = str(port).strip()
    if not host:
        host = "127.0.0.1"
    if "://" in host:
        host = host.rstrip("/")
        # Only append the port if host does not already end with one.
        tail = host.rsplit(":", 1)[-1]
        if tail.isdigit():
            return host
        return f"{host}:{port}" if port else host
    scheme = "http://"
    return f"{scheme}{host}:{port}" if port else f"{scheme}{host}"


def _probe_base(base: str):
    if not base:
        return False
    base = base.rstrip("/")
    code, _ = _http_get(f"{base}/health")
    return code is not None and 200 <= code < 500


def _discover_base(cli_base: str, flags_file: str):
    tried, warnings = [], []
    seen = set()

    def _try_candidate(candidate: str, label: str):
        if not candidate:
            return None
        base = candidate.rstrip("/")
        if not base or base in seen:
            return None
        seen.add(base)
        tried.append(base)
        if _probe_base(base):
            return base
        if label:
            warnings.append(f"{label} not responding: {base}")
        return None

    # Explicit CLI override: do not fall back further.
    if cli_base:
        base = _try_candidate(cli_base, "--base")
        return (base or ""), tried, warnings

    env_base = (os.getenv("COMFYVN_BASE") or "").strip()
    base = _try_candidate(env_base, "COMFYVN_BASE")
    if base:
        return base, tried, warnings

    cfg = ports_config.get_config()
    public_base = (cfg.get("public_base") or "").strip()
    base = _try_candidate(public_base, "server.public_base")
    if base:
        return base, tried, warnings

    host = str(cfg.get("host") or "127.0.0.1")
    raw_ports = cfg.get("ports") or []
    ports_source = "config.ports"

    norm_ports = []
    for item in raw_ports:
        try:
            norm_ports.append(str(int(item)))
        except (TypeError, ValueError):
            text = str(item).strip()
            if text:
                norm_ports.append(text)

    for p in norm_ports:
        label = f"{ports_source}[{p}]"
        base = _try_candidate(_compose_base(host, p), label)
        if base:
            return base, tried, warnings

    for fallback_port in ("8001", "8000"):
        base = _try_candidate(
            _compose_base("127.0.0.1", fallback_port), f"fallback[{fallback_port}]"
        )
        if base:
            return base, tried, warnings

    return "", tried, warnings


def main():
    ap = argparse.ArgumentParser(
        description="Check how current systems work (flags, routes, files)."
    )
    ap.add_argument(
        "--profile", required=True, help="Profile key in tools/check_profiles.json"
    )
    ap.add_argument("--conf", default=DEF_CONF)
    ap.add_argument("--flags-file", default=DEF_FLAGS)
    ap.add_argument("--base", default="")
    args = ap.parse_args()

    profiles = load_json(args.conf)
    profile = profiles.get(args.profile, {})
    base, tried, warnings = _discover_base(args.base, args.flags_file)
    out = {
        "ts": time.time(),
        "profile": args.profile,
        "base": base,
        "tried": tried,
        "warnings": warnings,
        "pass": True,
        "flags": [],
        "routes": [],
        "files": [],
        "notes": [],
    }

    if base:
        print(
            f"[check_current_system] base={base} tried={tried}",
            file=sys.stderr,
        )
    else:
        out["pass"] = False
        out["notes"].append("No reachable server base discovered.")
        print(
            f"[check_current_system] no reachable base; tried={tried}",
            file=sys.stderr,
        )
        print(json.dumps(out, indent=2))
        sys.exit(2)

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
    base = base.rstrip("/")
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
