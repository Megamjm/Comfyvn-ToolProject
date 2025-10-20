from PySide6.QtGui import QAction
# [ComfyVN AutoPatch | v0.8-BETA | 2025-10-13]
import os, sys, subprocess, logging
from comfyvn.logging_config import init_logging

LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
init_logging(LOG_DIR, filename="launcher.log")
logger = logging.getLogger(__name__)

def main():
    logger.info("ComfyVN Launcher starting…")
    try:
        install_log = os.path.join(LOG_DIR, "install", "install_report.log")
        if not os.path.exists(install_log):
            logger.info("Running installer…")
            subprocess.check_call([sys.executable, "-m", "comfyvn.scripts.install_manager"])
    except Exception as e:
        logger.warning("Installer step failed or was skipped: %s", e)

    logger.info("Launching GUI…")
    code = subprocess.call([sys.executable, "-m", "comfyvn.gui.main_window"])
    logger.info("GUI exited with code %s", code)

if __name__ == "__main__":
    main()