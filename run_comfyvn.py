import hashlib
import logging
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Optional, Tuple

from comfyvn.logging_config import init_logging as init_gui_logging

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"
REQUIREMENTS_HASH_FILE = VENV_DIR / ".requirements_hash"
BOOTSTRAP_FLAG = "COMFYVN_BOOTSTRAPPED"
LOGGER = logging.getLogger("comfyvn.launcher")


def log(message: str) -> None:
    LOGGER.info(message)
    print(f"[ComfyVN] {message}")


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
        raise RuntimeError("Virtual environment creation succeeded but python executable was not found.")
    return python_path, True


def run_command(command: list[str], *, cwd: Optional[Path] = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
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
    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "-r", str(REQUIREMENTS_FILE)])
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


def git_command(args: list[str], *, capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess[str]:
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

    result = git_command(["rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], check=False)
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
        remote_count_str, local_count_str = git_command(
            ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"]
        ).stdout.strip().split()
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
        log("Repository has uncommitted changes. Please update manually when convenient.")
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


def launch_app() -> None:
    gui_log_dir = REPO_ROOT / "logs"
    gui_log_dir.mkdir(parents=True, exist_ok=True)
    init_gui_logging(str(gui_log_dir), filename="gui.log")
    from PySide6.QtGui import QAction  # noqa: F401
    from comfyvn.gui.main_window import main

    log("🎨 Launching GUI and embedded backend …")
    main()


def main() -> None:
    configure_launcher_logging()
    bootstrap_environment()
    launch_app()


if __name__ == "__main__":
    main()
