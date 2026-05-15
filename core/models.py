"""Shared models used by the recorder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EncoderType(Enum):
    """Supported FFmpeg encoder modes."""

    H264 = ("H.264 (libx264)", "libx264")
    H265 = ("H.265 (libx265)", "libx265")
    H264_NVENC = ("H.264 (NVENC)", "h264_nvenc")
    H265_NVENC = ("H.265 (NVENC)", "hevc_nvenc")

    def __init__(self, label: str, ffmpeg_codec: str) -> None:
        self.label = label
        self.ffmpeg_codec = ffmpeg_codec

    @property
    def is_nvenc(self) -> bool:
        """Return whether the encoder uses NVIDIA NVENC."""
        return self in {self.H264_NVENC, self.H265_NVENC}


@dataclass(slots=True)
class RecorderSettings:
    """User-selected settings for a recording session."""

    capture_interval_seconds: float
    output_fps: int
    jpg_quality: int
    output_dir: Path
    frames_root: Path
    output_name: str
    ffmpeg_path: Path
    monitor_index: int
    encoder: EncoderType
    crf: int


@dataclass(slots=True)
class RuntimeDirectories:
    """Application directories created at startup."""

    app_root: Path
    log_dir: Path
    frames_dir: Path
    output_dir: Path


@dataclass(slots=True)
class ScreenInfo:
    """Description of a detected display."""

    index: int
    label: str
    width: int
    height: int
    is_primary: bool
    device_name: str
