#!/usr/bin/env python3

import os
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _bootstrap_repo_cwd() -> None:
    """Ensure Python resolves project-relative paths from the repository root."""
    try:
        current = Path.cwd().resolve()
    except FileNotFoundError:
        current = None
    if current != REPO_ROOT:
        os.chdir(REPO_ROOT)


_bootstrap_repo_cwd()

import argparse
import hashlib
import logging
import shutil
import subprocess
import types
import venv
from typing import Optional, Sequence, Tuple

from comfyvn.config import ports as ports_config
from comfyvn.config.baseurl_authority import (
    current_authority,
    find_open_port,
    write_runtime_authority,
)
from comfyvn.logging_config import init_logging as init_gui_logging
from comfyvn.server.bootstrap.headless import ensure_headless_ready
from setup import install_defaults as defaults_install

VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"
REQUIREMENTS_HASH_FILE = VENV_DIR / ".requirements_hash"
BOOTSTRAP_FLAG = "COMFYVN_BOOTSTRAPPED"
LOGGER = logging.getLogger("comfyvn.launcher")


AUTHORITY_DEFAULT = current_authority()
PORT_SETTINGS = ports_config.get_config()


def _dedupe_ports(values: Sequence[object]) -> list[int]:
    result: list[int] = []
    for value in values:
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if not 0 < port < 65536:
            continue
        if port not in result:
            result.append(port)
    return result


DEFAULT_PORT_CANDIDATES = _dedupe_ports(
    PORT_SETTINGS.get("ports")
    if isinstance(PORT_SETTINGS.get("ports"), (list, tuple))
    else []
)
if not DEFAULT_PORT_CANDIDATES:
    DEFAULT_PORT_CANDIDATES = [8001, 8000]

DEFAULT_SERVER_HOST = os.environ.get("COMFYVN_SERVER_HOST")
if DEFAULT_SERVER_HOST:
    DEFAULT_SERVER_HOST = DEFAULT_SERVER_HOST.strip()
else:
    DEFAULT_SERVER_HOST = str(
        PORT_SETTINGS.get("host") or AUTHORITY_DEFAULT.host
    ).strip()

ENV_PORT = os.environ.get("COMFYVN_SERVER_PORT")
try:
    DEFAULT_PORT_OVERRIDE = int(ENV_PORT) if ENV_PORT else None
except (TypeError, ValueError):
    DEFAULT_PORT_OVERRIDE = None

if DEFAULT_PORT_OVERRIDE and DEFAULT_PORT_OVERRIDE not in DEFAULT_PORT_CANDIDATES:
    DEFAULT_PORT_CANDIDATES.insert(0, DEFAULT_PORT_OVERRIDE)

DEFAULT_PORT_HELP = ", ".join(str(p) for p in DEFAULT_PORT_CANDIDATES)
DEFAULT_SERVER_APP = os.environ.get("COMFYVN_SERVER_APP", "comfyvn.server.app:app")
DEFAULT_SERVER_LOG_LEVEL = os.environ.get("COMFYVN_SERVER_LOG_LEVEL", "info")


def log(message: str) -> None:
    LOGGER.info(message)
    print(f"[ComfyVN] {message}")


_LOCAL_BIND_HOSTS = {
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "0",
    "*",
    "::",
    "[::]",
    "::1",
}


def _connect_host(host: str) -> str:
    lowered = host.strip().lower()
    if lowered in {"0.0.0.0", "0", "*"}:
        return "127.0.0.1"
    if lowered in {"::", "[::]"}:
        return "localhost"
    return host


def _is_port_free(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((host, int(port))) != 0
    except OSError:
        return False


def _select_server_port(
    host: str, requested_port: Optional[int], candidates: Sequence[int]
) -> tuple[int, bool]:
    candidate_list: list[int] = []
    for candidate in candidates:
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if not 0 < value < 65536:
            continue
        if value not in candidate_list:
            candidate_list.append(value)
    if not candidate_list:
        candidate_list = [8001, 8000]
    initial_port = (
        int(requested_port) if requested_port is not None else candidate_list[0]
    )
    lowered = host.strip().lower()
    connect_host = _connect_host(host)
    if lowered not in _LOCAL_BIND_HOSTS:
        return initial_port, False
    search_order = [initial_port, *[p for p in candidate_list if p != initial_port]]
    for port in search_order:
        if _is_port_free(connect_host, port):
            return port, port != initial_port
    fallback = find_open_port(connect_host, search_order[-1])
    return fallback, fallback != initial_port


def ensure_repo_cwd() -> None:
    _bootstrap_repo_cwd()


QT_STUB_INSTALLED = False


def qt_runtime_available() -> tuple[bool, str]:
    try:
        from PySide6.QtGui import QAction  # type: ignore

        _ = QAction
        return True, ""
    except Exception as exc:  # pragma: no cover - defensive headless path
        return False, str(exc)


def install_headless_qt_stub() -> None:
    global QT_STUB_INSTALLED
    if QT_STUB_INSTALLED:
        return
    QT_STUB_INSTALLED = True

    for name in list(sys.modules):
        if name == "PySide6" or name.startswith("PySide6."):
            sys.modules.pop(name, None)

    stub = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")

    class _HeadlessSignal:
        def connect(self, *_args, **_kwargs) -> None:
            return None

        def emit(self, *_args, **_kwargs) -> None:
            return None

    class _HeadlessAction:
        def __init__(self, *args, **_kwargs) -> None:
            self.text = args[0] if args else ""
            self.triggered = _HeadlessSignal()

        def setShortcut(self, *_args, **_kwargs) -> None:
            return None

        def setIcon(self, *_args, **_kwargs) -> None:
            return None

        def setObjectName(self, *_args, **_kwargs) -> None:
            return None

        def __getattr__(self, _name):
            def _noop(*_args, **_kwargs):
                return None

            return _noop

    qtgui.QAction = _HeadlessAction  # type: ignore[attr-defined]
    stub.QtGui = qtgui  # type: ignore[attr-defined]

    sys.modules["PySide6"] = stub
    sys.modules["PySide6.QtGui"] = qtgui


def configure_launcher_logging() -> None:
    logs_dir = REPO_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "launcher.log"
    if not LOGGER.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)


def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ComfyVN launcher and server utility.")
    parser.add_argument(
        "--server-only",
        "--headless",
        "--no-gui",
        action="store_true",
        dest="server_only",
        help="Run only the FastAPI server (skip the Qt GUI).",
    )
    parser.add_argument(
        "--server-host",
        "--host",
        dest="server_host",
        default=None,
        help=f"Host interface for the server (default: {DEFAULT_SERVER_HOST}).",
    )
    parser.add_argument(
        "--server-port",
        "--port",
        dest="server_port",
        type=int,
        default=None,
        help=f"TCP port for the server (roll-over order: {DEFAULT_PORT_HELP}).",
    )
    parser.add_argument(
        "--server-url",
        default=None,
        help="Override the server base URL the GUI connects to (implies remote mode).",
    )
    parser.add_argument(
        "--server-reload",
        action="store_true",
        help="Enable uvicorn reload (useful for development).",
    )
    parser.add_argument(
        "--server-workers",
        type=int,
        default=None,
        help="Number of uvicorn worker processes (default: uvicorn default).",
    )
    parser.add_argument(
        "--server-log-level",
        default=DEFAULT_SERVER_LOG_LEVEL,
        help=f"uvicorn log level (default: {DEFAULT_SERVER_LOG_LEVEL}).",
    )
    parser.add_argument(
        "--uvicorn-app",
        default=DEFAULT_SERVER_APP,
        help=f"ASGI app to run when using --server-only (default: {DEFAULT_SERVER_APP}).",
    )
    parser.add_argument(
        "--uvicorn-factory",
        action="store_true",
        help="Treat --uvicorn-app as a factory callable instead of an ASGI instance.",
    )
    parser.add_argument(
        "--no-server-autostart",
        action="store_true",
        help="Prevent the GUI from auto-starting a local server.",
    )
    parser.add_argument(
        "--install-defaults",
        action="store_true",
        help="Install default assets and exit.",
    )
    parser.add_argument(
        "--defaults-use-symlinks",
        action="store_true",
        help="Prefer symlinks when installing defaults (falls back to copying).",
    )
    parser.add_argument(
        "--defaults-dry-run",
        action="store_true",
        help="Preview default installation actions without writing to disk.",
    )
    parser.add_argument(
        "--defaults-force",
        action="store_true",
        help="Overwrite existing files when installing defaults.",
    )
    defaults_group = parser.add_mutually_exclusive_group()
    defaults_group.add_argument(
        "--include-sillytavern-extension",
        dest="include_sillytavern_extension",
        action="store_const",
        const=True,
        default=None,
        help="Include the SillyTavern bridge extension when installing defaults.",
    )
    defaults_group.add_argument(
        "--skip-sillytavern-extension",
        dest="include_sillytavern_extension",
        action="store_const",
        const=False,
        help="Skip the SillyTavern bridge extension when installing defaults.",
    )
    return parser.parse_args(argv)


def derive_server_base(host: str, port: int) -> str:
    lowered = host.strip().lower()
    if lowered in {"0.0.0.0", "0", "*"}:
        connect_host = "127.0.0.1"
    elif lowered in {"::", "[::]", "::0"}:
        connect_host = "localhost"
    else:
        connect_host = host
    return f"http://{connect_host}:{port}"


def apply_launcher_environment(args: argparse.Namespace) -> None:
    raw_config = ports_config.get_config()
    raw_ports = raw_config.get("ports")
    if isinstance(raw_ports, (list, tuple)):
        candidate_ports = _dedupe_ports(raw_ports)
    else:
        candidate_ports = list(DEFAULT_PORT_CANDIDATES)
    if not candidate_ports:
        candidate_ports = list(DEFAULT_PORT_CANDIDATES)
    if DEFAULT_PORT_OVERRIDE and DEFAULT_PORT_OVERRIDE not in candidate_ports:
        candidate_ports.insert(0, DEFAULT_PORT_OVERRIDE)
    public_base = raw_config.get("public_base")

    if args.server_host is None:
        args.server_host = str(raw_config.get("host") or DEFAULT_SERVER_HOST)

    if args.server_url:
        target_base = args.server_url.rstrip("/")
        if args.server_port is None:
            args.server_port = candidate_ports[0]
    else:
        requested_port = args.server_port if args.server_port is not None else None
        selected_port, rolled = _select_server_port(
            args.server_host,
            requested_port,
            candidate_ports,
        )
        if requested_port is not None and selected_port != requested_port:
            log(
                f"⚠️ Port {requested_port} unavailable on {_connect_host(args.server_host)}; rolling to {selected_port}."
            )
        elif requested_port is None and rolled:
            log(
                f"⚠️ Rolled server port to {selected_port} (preferred order: {', '.join(str(p) for p in candidate_ports)})."
            )
        args.server_port = selected_port
        if public_base:
            target_base = str(public_base).rstrip("/")
        else:
            target_base = derive_server_base(args.server_host, args.server_port)
        runtime_host = _connect_host(args.server_host)
        write_runtime_authority(runtime_host, args.server_port)
        ports_config.record_runtime_state(
            host=args.server_host,
            ports=candidate_ports,
            active_port=int(args.server_port),
            base_url=target_base,
            public_base=str(public_base) if public_base else None,
        )
        current_authority(refresh=True)

    os.environ["COMFYVN_SERVER_BASE"] = target_base
    os.environ["COMFYVN_BASE_URL"] = target_base
    os.environ["COMFYVN_SERVER_HOST"] = _connect_host(args.server_host)
    os.environ["COMFYVN_SERVER_PORT"] = str(args.server_port)

    if args.no_server_autostart or args.server_only:
        os.environ["COMFYVN_SERVER_AUTOSTART"] = "0"
    else:
        os.environ.setdefault("COMFYVN_SERVER_AUTOSTART", "1")

    os.environ["COMFYVN_SERVER_APP"] = args.uvicorn_app
    os.environ["COMFYVN_SERVER_LOG_LEVEL"] = args.server_log_level


def launch_server(
    app_path: str,
    host: str,
    port: int,
    *,
    log_level: str = "info",
    reload: bool = False,
    workers: Optional[int] = None,
    factory: bool = False,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - only when uvicorn missing
        raise RuntimeError(
            "uvicorn is required to start the ComfyVN backend. Install dependencies with `pip install -r requirements.txt`."
        ) from exc

    log(f"🚀 Starting ComfyVN server at http://{host}:{port} (app={app_path}) …")
    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "log_level": log_level,
        "reload": reload,
        "factory": factory,
    }
    if workers:
        uvicorn_kwargs["workers"] = workers
    uvicorn.run(app_path, **uvicorn_kwargs)


def running_inside_venv(venv_dir: Path) -> bool:
    try:
        return Path(sys.prefix).resolve() == venv_dir.resolve()
    except FileNotFoundError:
        return False


def venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    for name in ("python3", "python"):
        candidate = venv_dir / "bin" / name
        if candidate.exists():
            return candidate
    return venv_dir / "bin" / "python"


def ensure_virtualenv(venv_dir: Path) -> Tuple[Path, bool]:
    python_path = venv_python_path(venv_dir)
    if python_path.exists():
        return python_path, False

    log(f"Creating virtual environment at {venv_dir} …")
    builder = venv.EnvBuilder(with_pip=True, clear=False, upgrade=False)
    builder.create(venv_dir)
    python_path = venv_python_path(venv_dir)
    if not python_path.exists():
        raise RuntimeError(
            "Virtual environment creation succeeded but python executable was not found."
        )
    return python_path, True


def run_command(
    command: list[str], *, cwd: Optional[Path] = None, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def ensure_requirements(python_path: Path, force: bool = False) -> None:
    if not REQUIREMENTS_FILE.exists():
        return

    requirements_hash = hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()
    if not force and REQUIREMENTS_HASH_FILE.exists():
        if REQUIREMENTS_HASH_FILE.read_text().strip() == requirements_hash:
            return

    log("Installing Python dependencies …")
    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    run_command(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "-r",
            str(REQUIREMENTS_FILE),
        ]
    )
    REQUIREMENTS_HASH_FILE.write_text(requirements_hash)


def prompt_yes_no(message: str, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        log("Non-interactive session detected; skipping prompt.")
        return False

    prompt_suffix = "Y/n" if default else "y/N"
    while True:
        try:
            response = input(f"{message} [{prompt_suffix}]: ").strip().lower()
        except EOFError:
            return default
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        log("Please respond with 'y' or 'n'.")


def git_command(
    args: list[str], *, capture_output: bool = True, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=capture_output,
        check=check,
    )


def get_upstream_branch() -> Optional[str]:
    try:
        branch = git_command(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    except subprocess.CalledProcessError:
        return None

    result = git_command(
        ["rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], check=False
    )
    if result.returncode != 0:
        return None
    upstream = result.stdout.strip()
    return upstream or None


def prompt_for_git_update() -> None:
    if os.environ.get(BOOTSTRAP_FLAG) == "1":
        return

    if not (REPO_ROOT / ".git").exists():
        return

    if shutil.which("git") is None:
        log("Git not found; skipping update check.")
        return

    try:
        git_command(["fetch", "--quiet"], capture_output=False)
    except subprocess.CalledProcessError:
        log("Unable to fetch remote updates. Continuing without update.")
        return

    upstream = get_upstream_branch()
    if not upstream:
        log("No upstream branch configured; skipping update prompt.")
        return

    try:
        remote_count_str, local_count_str = (
            git_command(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
            .stdout.strip()
            .split()
        )
        remote_count = int(remote_count_str)
        local_count = int(local_count_str)
    except (ValueError, subprocess.CalledProcessError):
        log("Unable to determine update status. Skipping update prompt.")
        return

    if remote_count == 0:
        return

    dirty = False
    try:
        dirty = bool(git_command(["status", "--porcelain"]).stdout.strip())
    except subprocess.CalledProcessError:
        pass

    if dirty:
        log(
            "Repository has uncommitted changes. Please update manually when convenient."
        )
        return

    if local_count > 0:
        log("Local branch has commits not on the remote. Skipping automatic update.")
        return

    if prompt_yes_no("Updates are available. Pull latest changes now?", default=True):
        try:
            git_command(["pull", "--ff-only"], capture_output=False)
            log("Repository updated successfully.")
        except subprocess.CalledProcessError:
            log("Git pull failed. Please resolve the issue and retry.")


def install_defaults_flow(args: argparse.Namespace) -> int:
    include_silly = args.include_sillytavern_extension
    if include_silly is None:
        include_silly = prompt_yes_no(
            "Install SillyTavern bridge assets?", default=True
        )
    if include_silly and not defaults_install.SILLYTAVERN_SOURCE.exists():
        log("SillyTavern Extension assets not found; skipping installation.")
        include_silly = False
    if args.defaults_dry_run:
        log("Dry run: seeding ComfyVN default assets …")
    else:
        log("Seeding ComfyVN default assets …")
    try:
        summary = defaults_install.install_defaults(
            dry_run=args.defaults_dry_run,
            force=args.defaults_force,
            install_sillytavern=include_silly,
            use_symlinks=args.defaults_use_symlinks,
        )
    except Exception as exc:  # pragma: no cover - safety net
        log(f"Default asset installation failed: {exc}")
        LOGGER.exception("Default asset installation failed")
        return 1

    defaults_install.print_summary(
        summary,
        dry_run=args.defaults_dry_run,
        install_sillytavern=include_silly,
    )
    return 0


def bootstrap_environment() -> None:
    prompt_for_git_update()

    python_path, venv_created = ensure_virtualenv(VENV_DIR)
    ensure_requirements(python_path, force=venv_created)

    if not running_inside_venv(VENV_DIR):
        env = os.environ.copy()
        env[BOOTSTRAP_FLAG] = "1"
        command = [str(python_path), str(Path(__file__).resolve()), *sys.argv[1:]]
        log("Re-launching inside the virtual environment …")
        result = subprocess.call(command, env=env)
        sys.exit(result)


os.environ[BOOTSTRAP_FLAG] = "1"


def detect_render_support() -> tuple[bool, str]:
    """
    Determine whether the host appears capable of running the embedded backend.
    CPU-only operation is acceptable; we primarily guard catastrophic detection failures.
    """
    try:
        from comfyvn.core.gpu_manager import GPUManager  # type: ignore
    except Exception as exc:  # pragma: no cover - lazy import
        return False, f"gpu_manager import failed: {exc}"

    try:
        manager = GPUManager()
        devices = manager.list_all(refresh=True)
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"hardware detection failed: {exc}"

    if not devices:
        return False, "no compute devices detected"

    available = [dev for dev in devices if dev.get("available") is not False]
    if not available:
        return False, "detected devices are unavailable"

    return True, ""


def launch_app() -> None:
    gui_log_dir = REPO_ROOT / "logs"
    gui_log_dir.mkdir(parents=True, exist_ok=True)
    server_base = os.environ.get("COMFYVN_SERVER_BASE")
    if server_base:
        log(f"GUI target server: {server_base}")
    if os.environ.get("COMFYVN_SERVER_AUTOSTART") == "0":
        log("Auto-start for local server is disabled (COMFYVN_SERVER_AUTOSTART=0).")
    init_gui_logging(str(gui_log_dir), filename="gui.log")
    from PySide6.QtGui import QAction  # noqa: F401

    from comfyvn.gui.main_window import main

    log("🎨 Launching GUI and embedded backend …")
    try:
        main()
    except Exception as exc:  # pragma: no cover - GUI bootstrap guard
        log(f"GUI encountered a fatal error: {exc}")
        LOGGER.exception("GUI launch failed")
        sys.exit(1)


def main(argv: Optional[list[str]] = None) -> None:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    ensure_repo_cwd()
    configure_launcher_logging()
    args = parse_arguments(argv_list)
    if args.install_defaults:
        exit_code = install_defaults_flow(args)
        sys.exit(exit_code)
    bootstrap_environment()
    qt_available, qt_reason = qt_runtime_available()
    headless_stub_active = False
    if args.server_only:
        if not qt_available:
            install_headless_qt_stub()
            headless_stub_active = True
            log(
                f"Qt runtime unavailable ({qt_reason}). Installing a headless compatibility stub for server-only mode."
            )
    elif not qt_available:
        install_headless_qt_stub()
        headless_stub_active = True
        log(
            f"⚠️ Qt runtime unavailable ({qt_reason}). Switching to --server-only mode with a headless compatibility stub."
        )
        args.server_only = True

    apply_launcher_environment(args)
    headless_env_flag = os.environ.get("COMFYVN_HEADLESS", "").strip().lower()
    run_headless_bootstrap = args.server_only or headless_env_flag in {
        "1",
        "true",
        "yes",
    }
    if run_headless_bootstrap:
        ensure_headless_ready()
    supports_render = True
    render_reason = ""
    if not args.server_only:
        supports_render, render_reason = detect_render_support()
        if (not supports_render) and not args.server_url:
            log(
                f"⚠️ Render hardware check failed ({render_reason}). Skipping automatic backend launch."
            )
            os.environ["COMFYVN_SERVER_AUTOSTART"] = "0"
    if args.server_only:
        launch_server(
            args.uvicorn_app,
            args.server_host,
            args.server_port,
            log_level=args.server_log_level,
            reload=args.server_reload,
            workers=args.server_workers,
            factory=args.uvicorn_factory,
        )
        return
    if not supports_render and render_reason:
        log(
            "GUI will attach without a local backend. Configure a remote server via Settings → Compute / Server Endpoints."
        )
    launch_app()


if __name__ == "__main__":
    main()
