"""Background capture worker and controller."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from threading import Event

import cv2
import dxcam
from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.models import RecorderSettings
from ffmpeg.encoder import FFmpegEncoder
from utils.paths import build_session_directory, ensure_unique_video_path


class RecorderWorker(QObject):
    """Capture frames on a worker thread and encode them after stop."""

    started = Signal(str)
    status_changed = Signal(str)
    frame_saved = Signal(int, str)
    encoding_started = Signal(str)
    finished = Signal(bool, str, str)

    def __init__(self, settings: RecorderSettings) -> None:
        super().__init__()
        self._settings = settings
        self._logger = logging.getLogger("timelapse.recorder")
        self._stop_event = Event()
        self._resume_event = Event()
        self._resume_event.set()
        self._camera = None

    @Slot()
    def run(self) -> None:
        """Run the capture loop until a stop is requested."""
        session_dir: Path | None = None
        output_path: Path | None = None
        frame_count = 0

        try:
            started_at = datetime.now()
            session_dir = build_session_directory(self._settings.frames_root, started_at)
            self.started.emit(str(session_dir))
            self.status_changed.emit("Capture engine started")

            self._camera = self._create_camera()
            next_capture = time.monotonic()

            while not self._stop_event.is_set():
                if not self._resume_event.is_set():
                    if self._wait_until_resumed_or_stopped():
                        break
                    next_capture = time.monotonic()
                    continue

                delay = max(0.0, next_capture - time.monotonic())
                if self._wait_for_capture_window(delay):
                    break

                captured_at = datetime.now()
                frame = self._camera.grab()
                if frame is None:
                    self._logger.warning("dxcam returned an empty frame")
                    next_capture = time.monotonic() + self._settings.capture_interval_seconds
                    continue

                frame_count += 1
                frame_path = self._save_frame(session_dir, frame_count, captured_at, frame)
                self.frame_saved.emit(frame_count, str(frame_path))
                next_capture += self._settings.capture_interval_seconds

                if next_capture < time.monotonic():
                    next_capture = time.monotonic() + self._settings.capture_interval_seconds

            self.status_changed.emit("Capture stopped, preparing video")

            if frame_count == 0:
                self.finished.emit(False, "Recording stopped before any frames were captured.", "")
                return

            output_path = ensure_unique_video_path(
                self._settings.output_dir / f"{self._settings.output_name}.mp4"
            )
            self.encoding_started.emit(str(output_path))
            encoder = FFmpegEncoder()
            encoded_output = encoder.encode(
                frames_directory=session_dir,
                output_path=output_path,
                settings=self._settings,
            )
            self.finished.emit(
                True,
                f"Recording complete. Video saved to {encoded_output.name}.",
                str(encoded_output),
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Recorder worker failed")
            self.finished.emit(False, str(exc), str(output_path) if output_path else "")
        finally:
            self._release_camera()

    def stop(self) -> None:
        """Request the worker loop to stop."""
        self._stop_event.set()
        self._resume_event.set()

    def pause(self) -> None:
        """Pause frame capture without ending the recording session."""
        self._resume_event.clear()

    def resume(self) -> None:
        """Resume frame capture after a pause."""
        self._resume_event.set()

    def _create_camera(self):
        self._logger.info("Initializing dxcam for output index %s", self._settings.monitor_index)
        return dxcam.create(
            output_idx=self._settings.monitor_index,
            output_color="BGR",
            max_buffer_len=8,
        )

    def _save_frame(
        self,
        session_dir: Path,
        frame_index: int,
        captured_at: datetime,
        frame,
    ) -> Path:
        file_name = f"{frame_index:06d}_{captured_at:%Y%m%d_%H%M%S}.jpg"
        frame_path = session_dir / file_name
        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._settings.jpg_quality],
        )
        if not success:
            raise RuntimeError(f"OpenCV failed to encode frame {frame_index}.")

        frame_path.write_bytes(encoded.tobytes())
        self._logger.debug("Saved frame %s to %s", frame_index, frame_path)
        return frame_path

    def _release_camera(self) -> None:
        if self._camera is None:
            return

        for method_name in ("stop", "release"):
            method = getattr(self._camera, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:  # noqa: BLE001
                    self._logger.debug("Ignoring camera cleanup error from %s", method_name)

        self._camera = None

    def _wait_until_resumed_or_stopped(self) -> bool:
        self.status_changed.emit("Recording paused")
        while not self._stop_event.is_set():
            if self._resume_event.wait(0.1):
                self.status_changed.emit("Recording resumed")
                return False
        return True

    def _wait_for_capture_window(self, delay: float) -> bool:
        remaining = delay
        while remaining > 0:
            slice_seconds = min(0.1, remaining)
            if self._stop_event.wait(slice_seconds):
                return True
            if not self._resume_event.is_set():
                return False
            remaining -= slice_seconds
        return self._stop_event.is_set()


class RecorderController(QObject):
    """Manage the recorder worker and its QThread lifecycle."""

    status_changed = Signal(str)
    frame_count_changed = Signal(int)
    recording_state_changed = Signal(bool)
    pause_state_changed = Signal(bool)
    session_directory_changed = Signal(str)
    output_ready = Signal(str)
    failure = Signal(str)
    recording_finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._logger = logging.getLogger("timelapse.controller")
        self._thread: QThread | None = None
        self._worker: RecorderWorker | None = None
        self._is_recording = False
        self._is_paused = False

    @property
    def is_recording(self) -> bool:
        """Return whether a recording session is active."""
        return self._is_recording

    @property
    def is_paused(self) -> bool:
        """Return whether the active recording is paused."""
        return self._is_paused

    def start_recording(self, settings: RecorderSettings) -> None:
        """Create the worker thread and start recording."""
        if self._is_recording:
            raise RuntimeError("A recording is already running.")

        thread = QThread()
        worker = RecorderWorker(settings)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self.session_directory_changed.emit)
        worker.started.connect(lambda _: self.status_changed.emit("Recording in progress"))
        worker.status_changed.connect(self.status_changed.emit)
        worker.frame_saved.connect(self._handle_frame_saved)
        worker.encoding_started.connect(
            lambda path: self.status_changed.emit(f"Encoding video to {path}")
        )
        worker.finished.connect(self._handle_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_worker_thread)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        self._is_recording = True
        self._is_paused = False
        self.recording_state_changed.emit(True)
        self.pause_state_changed.emit(False)
        self.status_changed.emit("Starting recorder thread")
        thread.start()

    def stop_recording(self) -> None:
        """Request a graceful stop."""
        if not self._is_recording or self._worker is None:
            return

        self.status_changed.emit("Stopping capture loop")
        self._worker.stop()

    def pause_recording(self) -> None:
        """Pause an active recording session."""
        if not self._is_recording or self._is_paused or self._worker is None:
            return

        self._is_paused = True
        self._worker.pause()
        self.pause_state_changed.emit(True)

    def resume_recording(self) -> None:
        """Resume a paused recording session."""
        if not self._is_recording or not self._is_paused or self._worker is None:
            return

        self._is_paused = False
        self._worker.resume()
        self.pause_state_changed.emit(False)

    def shutdown(self, timeout_ms: int = 15_000) -> bool:
        """Stop an active recording and wait for the worker thread to finish."""
        if self._worker is not None:
            self._worker.stop()

        if self._thread is None or not self._thread.isRunning():
            return True

        return self._thread.wait(timeout_ms)

    @Slot(int, str)
    def _handle_frame_saved(self, frame_count: int, _path: str) -> None:
        self.frame_count_changed.emit(frame_count)
        if frame_count == 1 or frame_count % 10 == 0:
            self.status_changed.emit(f"Captured {frame_count} frame(s)")

    @Slot(bool, str, str)
    def _handle_worker_finished(self, success: bool, message: str, output_path: str) -> None:
        self._is_recording = False
        self._is_paused = False
        self.recording_state_changed.emit(False)
        self.pause_state_changed.emit(False)
        self.recording_finished.emit(success, message)

        if success:
            if output_path:
                self.output_ready.emit(output_path)
            self.status_changed.emit(message)
        else:
            self.failure.emit(message)
            self.status_changed.emit("Recording failed")

    @Slot()
    def _cleanup_worker_thread(self) -> None:
        self._logger.debug("Recorder thread finished")
        self._worker = None
        self._thread = None
