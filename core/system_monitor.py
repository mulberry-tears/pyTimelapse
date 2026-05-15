"""Runtime CPU and memory monitoring."""

from __future__ import annotations

import psutil
from PySide6.QtCore import QObject, QTimer, Signal


class CpuMonitor(QObject):
    """Emit periodic CPU and memory usage strings for the GUI."""

    metrics_changed = Signal(str)

    def __init__(self, interval_ms: int = 1500, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)
        self._process = psutil.Process()
        self._process.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        """Start periodic monitoring."""
        self._timer.start()
        self._poll()

    def stop(self) -> None:
        """Stop periodic monitoring."""
        self._timer.stop()

    def _poll(self) -> None:
        app_cpu = self._process.cpu_percent(interval=None)
        system_cpu = psutil.cpu_percent(interval=None)
        memory_mb = self._process.memory_info().rss / (1024 * 1024)
        self.metrics_changed.emit(
            f"App {app_cpu:.1f}% | System {system_cpu:.1f}% | RAM {memory_mb:.0f} MB"
        )
