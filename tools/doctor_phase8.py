"""
Doctor Phase 8 — integration and determinism audit helper.

Usage:
    python tools/doctor_phase8.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from fastapi.routing import APIRoute, APIWebSocketRoute

LOGGER = logging.getLogger("doctor.phase8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_qt_stub() -> None:
    """Install lightweight PySide6 stubs so create_app() loads in CI/headless."""

    try:
        import PySide6.QtWidgets  # type: ignore

        return
    except Exception:
        pass

    stub = types.ModuleType("PySide6")

    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Signal = lambda *args, **kwargs: (lambda *a, **k: None)  # type: ignore
    qtcore.Slot = lambda *args, **kwargs: (lambda func: func)  # type: ignore
    qtcore.QObject = type("QObject", (), {"__init__": lambda self, *a, **k: None})
    qtcore.QTimer = type(
        "QTimer",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "start": lambda self, *a, **k: None,
            "setInterval": lambda self, *a, **k: None,
            "stop": lambda self, *a, **k: None,
        },
    )

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type(
        "QAction",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "triggered": type("Signal", (), {"connect": lambda self, *a, **k: None})(),
        },
    )

    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    qtwidgets.QSystemTrayIcon = type(
        "QSystemTrayIcon",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "setVisible": lambda self, *a, **k: None,
            "show": lambda self, *a, **k: None,
        },
    )
    qtwidgets.QMenu = type(
        "QMenu",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "addAction": lambda self, *a, **k: None,
        },
    )
    qtwidgets.QApplication = type(
        "QApplication",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "instance": staticmethod(lambda: None),
            "quit": staticmethod(lambda: None),
            "style": staticmethod(
                lambda: type(
                    "Style",
                    (),
                    {"standardIcon": lambda self, *a, **k: None},
                )()
            ),
        },
    )

    stub.QtCore = qtcore  # type: ignore[attr-defined]
    stub.QtGui = qtgui  # type: ignore[attr-defined]
    stub.QtWidgets = qtwidgets  # type: ignore[attr-defined]

    sys.modules.setdefault("PySide6", stub)
    sys.modules.setdefault("PySide6.QtCore", qtcore)
    sys.modules.setdefault("PySide6.QtGui", qtgui)
    sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)


def _build_app():
    _ensure_qt_stub()
    os.environ.setdefault("COMFYVN_LOG_LEVEL", "ERROR")
    from comfyvn.server.app import create_app

    return create_app()


def _route_signatures(routes: Iterable[Any]) -> Dict[Tuple[str, str], str]:
    signatures: Dict[Tuple[str, str], str] = {}
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            signatures[(route.path, method)] = route.name
    return signatures


def _check_routes(app) -> Dict[str, Any]:
    signatures = _route_signatures(app.routes)
    duplicates: List[Dict[str, str]] = []

    seen: Dict[Tuple[str, str], str] = {}
    for (path, method), name in signatures.items():
        if (path, method) in seen:
            duplicates.append(
                {
                    "path": path,
                    "method": method,
                    "first": seen[(path, method)],
                    "second": name,
                }
            )
        else:
            seen[(path, method)] = name

    required_signatures = {
        ("/health", "GET"),
        ("/status", "GET"),
        ("/system/metrics", "GET"),
        ("/api/weather/state", "GET"),
        ("/api/weather/state", "POST"),
        ("/api/props/anchors", "GET"),
        ("/api/props/ensure", "POST"),
        ("/api/props/apply", "POST"),
        ("/api/battle/resolve", "POST"),
        ("/api/battle/simulate", "POST"),
        ("/api/modder/hooks", "GET"),
        ("/api/modder/hooks/history", "GET"),
        ("/api/narrator/status", "GET"),
        ("/api/viewer/mini/snapshot", "GET"),
        ("/api/viewer/mini/refresh", "POST"),
        ("/api/providers/gpu/public/catalog", "GET"),
        ("/api/providers/gpu/public/runpod/health", "POST"),
        ("/api/pov/worlds", "GET"),
        ("/api/pov/confirm_switch", "POST"),
    }

    missing = sorted(
        [
            {"path": path, "method": method}
            for path, method in required_signatures
            if (path, method) not in signatures
        ],
        key=lambda item: (item["path"], item["method"]),
    )

    ws_required = {"/api/modder/hooks/ws"}
    ws_present = {
        route.path for route in app.routes if isinstance(route, APIWebSocketRoute)
    }
    ws_missing = sorted(path for path in ws_required if path not in ws_present)

    return {
        "ok": not duplicates and not missing and not ws_missing,
        "duplicates": duplicates,
        "missing": missing,
        "missing_ws": ws_missing,
        "route_count": len(signatures),
    }


def _check_feature_flags() -> Dict[str, Any]:
    from comfyvn.config import feature_flags

    flags = feature_flags.load_feature_flags(refresh=True)
    expectations = {
        "enable_policy_enforcer": True,
        "enable_comfy_bridge_hardening": False,
        "enable_comfy_preview_stream": False,
        "enable_compute": True,
        "enable_sillytavern_bridge": False,
        "enable_remote_installer": False,
        "enable_extension_market": False,
        "enable_extension_market_uploads": False,
        "enable_public_gpu": False,
        "enable_public_image_video": False,
        "enable_public_image_providers": False,
        "enable_public_video_providers": False,
        "enable_public_llm": False,
        "enable_public_translate": False,
        "enable_mini_vn": True,
        "enable_viewer_webmode": True,
        "enable_weather_planner": True,
        "enable_weather": True,
        "enable_worldlines": False,
        "enable_timeline_overlay": False,
        "enable_depth2d": False,
        "enable_battle": True,
        "enable_props": False,
        "enable_rating_api": True,
        "enable_llm_role_mapping": False,
        "enable_narrator": False,
        "enable_playground": False,
        "enable_stage3d": False,
        "enable_security_sandbox_guard": True,
        "enable_collaboration": True,
    }

    mismatches = []
    missing_keys = []
    for name, expected in expectations.items():
        if name not in flags:
            missing_keys.append(name)
            continue
        if bool(flags[name]) != bool(expected):
            mismatches.append(
                {
                    "feature": name,
                    "expected": bool(expected),
                    "actual": bool(flags[name]),
                }
            )

    return {
        "ok": not mismatches and not missing_keys,
        "missing": sorted(missing_keys),
        "mismatches": mismatches,
    }


def _check_modder_hooks() -> Dict[str, Any]:
    from comfyvn.core import modder_hooks

    required_hooks = {
        "on_scene_enter",
        "on_choice_render",
        "on_asset_registered",
        "on_asset_saved",
        "on_asset_removed",
        "on_asset_sidecar_written",
        "on_prop_applied",
        "on_weather_changed",
        "on_worldline_diff",
        "on_worldline_merge",
        "on_worldline_created",
        "on_snapshot",
        "on_battle_resolved",
        "on_battle_simulated",
        "on_rating_decision",
        "on_rating_override",
        "on_rating_acknowledged",
        "on_narrator_proposal",
        "on_narrator_apply",
    }

    available = set(modder_hooks.HOOK_SPECS.keys())
    missing = sorted(required_hooks - available)

    return {
        "ok": not missing,
        "missing": missing,
        "available": sorted(available),
    }


def _check_security() -> Dict[str, Any]:
    gitignore = Path(".gitignore")
    secrets_gitignored = False
    if gitignore.exists():
        secrets_gitignored = any(
            line.strip() == "config/comfyvn.secrets.json"
            for line in gitignore.read_text(encoding="utf-8").splitlines()
        )
    return {"ok": secrets_gitignored, "secrets_gitignored": secrets_gitignored}


def run_doctor() -> Dict[str, Any]:
    app = _build_app()

    report: Dict[str, Any] = {
        "routes": _check_routes(app),
        "feature_flags": _check_feature_flags(),
        "modder_hooks": _check_modder_hooks(),
        "security": _check_security(),
    }

    report["pass"] = all(
        section.get("ok", False)
        for section in report.values()
        if isinstance(section, dict)
    )
    return report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Doctor Phase 8 checks.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON (default: compact).",
    )
    args = parser.parse_args(argv)

    report = run_doctor()
    json.dump(
        report,
        sys.stdout,
        indent=2 if args.pretty else None,
        sort_keys=bool(args.pretty),
    )
    sys.stdout.write("\n")
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
