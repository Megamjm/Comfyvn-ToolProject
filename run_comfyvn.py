import os
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
import venv
from typing import Optional, Tuple

from comfyvn.config.baseurl_authority import current_authority, write_runtime_authority
from comfyvn.logging_config import init_logging as init_gui_logging
from setup import install_defaults as defaults_install

VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"
REQUIREMENTS_HASH_FILE = VENV_DIR / ".requirements_hash"
BOOTSTRAP_FLAG = "COMFYVN_BOOTSTRAPPED"
LOGGER = logging.getLogger("comfyvn.launcher")


AUTHORITY_DEFAULT = current_authority()
DEFAULT_SERVER_HOST = os.environ.get(
    "COMFYVN_SERVER_HOST", AUTHORITY_DEFAULT.host
).strip()
ENV_PORT = os.environ.get("COMFYVN_SERVER_PORT")
try:
    DEFAULT_SERVER_PORT = int(ENV_PORT) if ENV_PORT else AUTHORITY_DEFAULT.port
except (TypeError, ValueError):
    DEFAULT_SERVER_PORT = AUTHORITY_DEFAULT.port
DEFAULT_SERVER_APP = os.environ.get("COMFYVN_SERVER_APP", "comfyvn.server.app:app")
DEFAULT_SERVER_LOG_LEVEL = os.environ.get("COMFYVN_SERVER_LOG_LEVEL", "info")


def log(message: str) -> None:
    LOGGER.info(message)
    print(f"[ComfyVN] {message}")


def ensure_repo_cwd() -> None:
    _bootstrap_repo_cwd()


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
        default=DEFAULT_SERVER_HOST,
        help=f"Host interface for the server (default: {DEFAULT_SERVER_HOST}).",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=DEFAULT_SERVER_PORT,
        help=f"TCP port for the server (default: {DEFAULT_SERVER_PORT}).",
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
    if args.server_url:
        target_base = args.server_url.rstrip("/")
    else:
        target_base = derive_server_base(args.server_host, args.server_port)
        write_runtime_authority(args.server_host, args.server_port)
        current_authority(refresh=True)

    os.environ["COMFYVN_SERVER_BASE"] = target_base
    os.environ["COMFYVN_BASE_URL"] = target_base
    os.environ["COMFYVN_SERVER_HOST"] = args.server_host
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
    apply_launcher_environment(args)
    bootstrap_environment()
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
