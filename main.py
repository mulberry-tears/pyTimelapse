"""Application entry point for the Windows timelapse recorder."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from utils.logging_config import setup_logging
from utils.paths import ensure_runtime_directories
from utils.windows import set_dpi_awareness


def main() -> int:
    """Start the Qt application."""
    directories = ensure_runtime_directories()
    setup_logging(directories.log_dir)
    logger = logging.getLogger("timelapse")
    logger.info("Starting Timelapse Screen Recorder")

    set_dpi_awareness()

    app = QApplication(sys.argv)
    app.setApplicationName("Timelapse Screen Recorder")
    app.setStyle("Fusion")

    window = MainWindow(directories=directories)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
