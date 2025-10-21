from __future__ import annotations

import os
# comfyvn/core/remote_compute.py
import subprocess

from PySide6.QtGui import QAction


def run_remote(host: str, cmd: str):
    """Placeholder remote execution — extend with paramiko or REST later."""
    try:
        return subprocess.check_output(["ssh", host, cmd], text=True)
    except Exception as e:
        return f"ERR:{e}"


def sync_assets(host: str, remote_path: str = "~/comfyvn_assets"):
    os.system(f"scp -r comfyvn/data/assets.json {host}:{remote_path}/assets.json")
    return True
