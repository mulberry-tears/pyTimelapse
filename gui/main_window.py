"""Main application window."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.capture_service import RecorderController
from core.models import EncoderType, RecorderSettings, RuntimeDirectories, ScreenInfo
from core.system_monitor import CpuMonitor
from ffmpeg.encoder import FFmpegEncoder
from utils.paths import sanitize_file_name
from utils.windows import enumerate_monitors, find_bundled_ffmpeg, find_winget_ffmpeg


class MainWindow(QMainWindow):
    """Primary desktop window for the recorder."""

    def __init__(self, directories: RuntimeDirectories) -> None:
        super().__init__()
        self._directories = directories
        self._logger = logging.getLogger("timelapse.gui")
        self._controller = RecorderController()
        self._cpu_monitor = CpuMonitor(interval_ms=1500, parent=self)
        self._monitors: list[ScreenInfo] = []
        self._recording_started_at: datetime | None = None
        self._paused_started_at: datetime | None = None
        self._total_paused_seconds = 0.0
        self._is_paused = False
        self._latest_frame_count = 0

        self.setWindowTitle("Timelapse Screen Recorder")
        self.resize(980, 720)
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._load_defaults()
        self._refresh_monitors()
        self._cpu_monitor.start()

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        control_group = QGroupBox("Recording Controls")
        control_layout = QGridLayout(control_group)
        control_layout.setHorizontalSpacing(20)
        control_layout.setVerticalSpacing(12)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 3600.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setSuffix(" s")

        self.output_fps_spin = QSpinBox()
        self.output_fps_spin.setRange(1, 120)

        self.jpg_quality_spin = QSpinBox()
        self.jpg_quality_spin.setRange(50, 100)

        self.codec_combo = QComboBox()
        for encoder in EncoderType:
            self.codec_combo.addItem(encoder.label, encoder)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)

        self.monitor_combo = QComboBox()
        self.refresh_monitors_button = QPushButton("Refresh Displays")

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("timelapse_recording")

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setReadOnly(True)
        self.output_dir_button = QPushButton("Browse")

        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_button = QPushButton("Browse")

        control_layout.addWidget(QLabel("Capture interval"), 0, 0)
        control_layout.addWidget(self.interval_spin, 0, 1)
        control_layout.addWidget(QLabel("Output FPS"), 0, 2)
        control_layout.addWidget(self.output_fps_spin, 0, 3)

        control_layout.addWidget(QLabel("JPEG quality"), 1, 0)
        control_layout.addWidget(self.jpg_quality_spin, 1, 1)
        control_layout.addWidget(QLabel("Codec"), 1, 2)
        control_layout.addWidget(self.codec_combo, 1, 3)

        control_layout.addWidget(QLabel("CRF / CQ"), 2, 0)
        control_layout.addWidget(self.crf_spin, 2, 1)
        control_layout.addWidget(QLabel("Display"), 2, 2)
        control_layout.addWidget(self.monitor_combo, 2, 3)
        control_layout.addWidget(self.refresh_monitors_button, 2, 4)

        output_name_row = QWidget()
        output_name_layout = QHBoxLayout(output_name_row)
        output_name_layout.setContentsMargins(0, 0, 0, 0)
        output_name_layout.addWidget(self.output_name_edit)
        control_layout.addWidget(QLabel("Video file name"), 3, 0)
        control_layout.addWidget(output_name_row, 3, 1, 1, 4)

        output_dir_row = QWidget()
        output_dir_layout = QHBoxLayout(output_dir_row)
        output_dir_layout.setContentsMargins(0, 0, 0, 0)
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.output_dir_button)
        control_layout.addWidget(QLabel("Output directory"), 4, 0)
        control_layout.addWidget(output_dir_row, 4, 1, 1, 4)

        ffmpeg_row = QWidget()
        ffmpeg_layout = QHBoxLayout(ffmpeg_row)
        ffmpeg_layout.setContentsMargins(0, 0, 0, 0)
        ffmpeg_layout.addWidget(self.ffmpeg_path_edit)
        ffmpeg_layout.addWidget(self.ffmpeg_path_button)
        control_layout.addWidget(QLabel("FFmpeg executable"), 5, 0)
        control_layout.addWidget(ffmpeg_row, 5, 1, 1, 4)

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(12)
        self.start_button = QPushButton("Start Recording")
        self.pause_button = QPushButton("Pause Recording")
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setEnabled(False)
        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.pause_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addStretch(1)

        status_group = QGroupBox("Live Status")
        status_layout = QFormLayout(status_group)
        status_layout.setHorizontalSpacing(24)
        status_layout.setVerticalSpacing(10)

        self.status_value = QLabel("Idle")
        self.elapsed_value = QLabel("00:00:00")
        self.frame_count_value = QLabel("0")
        self.cpu_value = QLabel("Waiting for metrics")
        self.frames_path_value = QLabel(str(self._directories.frames_dir))
        self.output_path_value = QLabel(str(self._directories.output_dir))
        self.open_frames_button = QPushButton("Open Folder")
        self.open_output_button = QPushButton("Open Folder")

        self.status_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.frames_path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.output_path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)

        status_layout.addRow("State", self.status_value)
        status_layout.addRow("Elapsed", self.elapsed_value)
        status_layout.addRow("Frames", self.frame_count_value)
        status_layout.addRow("CPU / RAM", self.cpu_value)
        status_layout.addRow("Frames root", self._build_path_row(self.frames_path_value, self.open_frames_button))
        status_layout.addRow("Last output", self._build_path_row(self.output_path_value, self.open_output_button))

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)

        layout.addWidget(control_group)
        layout.addWidget(buttons_row)
        layout.addWidget(status_group)
        layout.addWidget(self.log_view, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar(self))

        refresh_action = QAction("Refresh displays", self)
        refresh_action.triggered.connect(self._refresh_monitors)
        self.addAction(refresh_action)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self._start_recording)
        self.pause_button.clicked.connect(self._toggle_pause_recording)
        self.stop_button.clicked.connect(self._stop_recording)
        self.output_dir_button.clicked.connect(self._choose_output_dir)
        self.ffmpeg_path_button.clicked.connect(self._choose_ffmpeg_path)
        self.refresh_monitors_button.clicked.connect(self._refresh_monitors)
        self.open_frames_button.clicked.connect(self._open_frames_location)
        self.open_output_button.clicked.connect(self._open_output_location)

        self._controller.status_changed.connect(self._set_status)
        self._controller.frame_count_changed.connect(self._update_frame_count)
        self._controller.recording_state_changed.connect(self._update_recording_state)
        self._controller.pause_state_changed.connect(self._update_pause_state)
        self._controller.session_directory_changed.connect(self._update_session_directory)
        self._controller.output_ready.connect(self._handle_output_ready)
        self._controller.failure.connect(self._handle_failure)
        self._controller.recording_finished.connect(self._handle_recording_finished)

        self._cpu_monitor.metrics_changed.connect(self.cpu_value.setText)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #13161c;
                color: #eef2f7;
                font-size: 13px;
            }
            QMainWindow {
                background: #13161c;
            }
            QGroupBox {
                border: 1px solid #273142;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 14px;
                font-weight: 600;
                background: #181d26;
            }
            QGroupBox::title {
                left: 12px;
                padding: 0 6px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
                background: #0f1319;
                border: 1px solid #2e3c52;
                border-radius: 6px;
                padding: 6px 8px;
                min-height: 18px;
            }
            QPushButton {
                background: #2468f2;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                min-width: 120px;
                font-weight: 600;
            }
            QPushButton:disabled {
                background: #3a4250;
                color: #9aa4b2;
            }
            QPushButton:hover:!disabled {
                background: #2f78ff;
            }
            QLabel {
                min-height: 18px;
            }
            QStatusBar {
                background: #181d26;
                color: #d3d9e2;
            }
            """
        )

    def _load_defaults(self) -> None:
        self.interval_spin.setValue(5.0)
        self.output_fps_spin.setValue(30)
        self.jpg_quality_spin.setValue(90)
        self.crf_spin.setValue(23)
        self.output_name_edit.setText(f"timelapse_{datetime.now():%Y%m%d_%H%M%S}")
        self.output_dir_edit.setText(str(self._directories.output_dir))
        self.ffmpeg_path_edit.setText(
            str(find_bundled_ffmpeg() or shutil.which("ffmpeg") or find_winget_ffmpeg() or "ffmpeg")
        )
        self._append_log("Application initialized")

    def _build_path_row(self, label: QLabel, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(label, 1)
        layout.addWidget(button)
        return row

    def _refresh_monitors(self) -> None:
        self._monitors = enumerate_monitors()
        self.monitor_combo.clear()

        for monitor in self._monitors:
            self.monitor_combo.addItem(monitor.label, monitor.index)

        if not self._monitors:
            self.monitor_combo.addItem("No displays detected", -1)
            self.start_button.setEnabled(False)
            self._append_log("No displays detected")
            return

        self.start_button.setEnabled(not self._controller.is_recording)
        self._append_log(f"Detected {len(self._monitors)} display(s)")

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select output directory",
            self.output_dir_edit.text(),
        )
        if directory:
            self.output_dir_edit.setText(directory)

    def _choose_ffmpeg_path(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ffmpeg executable",
            self.ffmpeg_path_edit.text(),
            "Executable (*.exe);;All files (*)",
        )
        if file_path:
            self.ffmpeg_path_edit.setText(file_path)

    def _open_frames_location(self) -> None:
        self._open_path(Path(self.frames_path_value.text()))

    def _open_output_location(self) -> None:
        self._open_path(Path(self.output_path_value.text()))

    def _open_path(self, path: Path) -> None:
        target = path if path.is_dir() else path.parent
        target.mkdir(parents=True, exist_ok=True)

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            try:
                os.startfile(target)
            except OSError as exc:
                QMessageBox.warning(self, "Open folder failed", str(exc))

    def _start_recording(self) -> None:
        if self._controller.is_recording:
            return

        try:
            settings = self._build_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return

        self._latest_frame_count = 0
        self._total_paused_seconds = 0.0
        self._paused_started_at = None
        self._is_paused = False
        self.frame_count_value.setText("0")
        self.output_path_value.setText(str(settings.output_dir))
        self._controller.start_recording(settings)

    def _stop_recording(self) -> None:
        if not self._controller.is_recording:
            return

        self._set_status("Stopping recording...")
        self._append_log("Stop requested by user")
        self._controller.stop_recording()

    def _toggle_pause_recording(self) -> None:
        if not self._controller.is_recording:
            return

        if self._controller.is_paused:
            self._append_log("Resume requested by user")
            self._controller.resume_recording()
            return

        self._append_log("Pause requested by user")
        self._controller.pause_recording()

    def _build_settings(self) -> RecorderSettings:
        output_name = sanitize_file_name(self.output_name_edit.text().strip())
        if not output_name:
            raise ValueError("Output video name cannot be empty.")

        output_dir = Path(self.output_dir_edit.text().strip() or self._directories.output_dir)
        ffmpeg_path = Path(self.ffmpeg_path_edit.text().strip() or "ffmpeg")
        monitor_index = self.monitor_combo.currentData()

        if monitor_index is None or monitor_index < 0:
            raise ValueError("Select a valid display before starting.")

        if not FFmpegEncoder.is_available(ffmpeg_path):
            raise ValueError(
                "FFmpeg executable was not found. Install FFmpeg or select ffmpeg.exe in the GUI."
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        return RecorderSettings(
            capture_interval_seconds=self.interval_spin.value(),
            output_fps=self.output_fps_spin.value(),
            jpg_quality=self.jpg_quality_spin.value(),
            output_dir=output_dir,
            frames_root=self._directories.frames_dir,
            output_name=output_name,
            ffmpeg_path=ffmpeg_path,
            monitor_index=int(monitor_index),
            encoder=self.codec_combo.currentData(),
            crf=self.crf_spin.value(),
        )

    def _set_status(self, message: str) -> None:
        self.status_value.setText(message)
        self.statusBar().showMessage(message, 5000)
        self._append_log(message)

    def _update_frame_count(self, frame_count: int) -> None:
        self._latest_frame_count = frame_count
        self.frame_count_value.setText(str(frame_count))

    def _update_recording_state(self, is_recording: bool) -> None:
        self.start_button.setEnabled(not is_recording and bool(self._monitors))
        self.pause_button.setEnabled(is_recording)
        self.stop_button.setEnabled(is_recording)

        for widget in (
            self.interval_spin,
            self.output_fps_spin,
            self.jpg_quality_spin,
            self.codec_combo,
            self.crf_spin,
            self.monitor_combo,
            self.output_name_edit,
            self.output_dir_edit,
            self.output_dir_button,
            self.ffmpeg_path_edit,
            self.ffmpeg_path_button,
            self.refresh_monitors_button,
        ):
            widget.setEnabled(not is_recording)

        if is_recording:
            self._recording_started_at = datetime.now()
            self._paused_started_at = None
            self._total_paused_seconds = 0.0
            self._is_paused = False
            self.pause_button.setText("Pause Recording")
            self._elapsed_timer.start()
        else:
            self._elapsed_timer.stop()
            self._recording_started_at = None
            self._paused_started_at = None
            self._total_paused_seconds = 0.0
            self._is_paused = False
            self.pause_button.setText("Pause Recording")
            self.elapsed_value.setText("00:00:00")

    def _update_pause_state(self, is_paused: bool) -> None:
        self._is_paused = is_paused
        self.pause_button.setText("Resume Recording" if is_paused else "Pause Recording")

        if is_paused:
            self._paused_started_at = datetime.now()
            return

        if self._paused_started_at is not None:
            paused_delta = datetime.now() - self._paused_started_at
            self._total_paused_seconds += paused_delta.total_seconds()
            self._paused_started_at = None

        self._update_elapsed()

    def _update_session_directory(self, session_directory: str) -> None:
        self.frames_path_value.setText(session_directory)
        self._append_log(f"Frames will be saved to {session_directory}")

    def _handle_output_ready(self, output_path: str) -> None:
        self.output_path_value.setText(output_path)
        self._append_log(f"Output ready: {output_path}")

    def _handle_failure(self, message: str) -> None:
        self._append_log(f"Error: {message}")
        QMessageBox.critical(self, "Recording error", message)

    def _handle_recording_finished(self, success: bool, message: str) -> None:
        if success:
            self._set_status(message)
        else:
            self.status_value.setText(message)
        self._append_log(f"Frames captured: {self._latest_frame_count}")

    def _update_elapsed(self) -> None:
        if self._recording_started_at is None:
            self.elapsed_value.setText("00:00:00")
            return

        elapsed_reference = self._paused_started_at or datetime.now()
        elapsed = elapsed_reference - self._recording_started_at
        elapsed_seconds = max(0, int(elapsed.total_seconds() - self._total_paused_seconds))
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.elapsed_value.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")
        self._logger.debug(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._controller.is_recording:
            answer = QMessageBox.question(
                self,
                "Stop recording",
                "A recording is still running. Stop it and exit?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._controller.stop_recording()
            if not self._controller.shutdown():
                QMessageBox.warning(
                    self,
                    "Recorder busy",
                    "The recorder is still shutting down. Wait for encoding to finish, then close again.",
                )
                event.ignore()
                return

        self._cpu_monitor.stop()
        event.accept()
