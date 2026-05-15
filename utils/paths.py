"""Path helpers for runtime directories and output naming."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from core.models import RuntimeDirectories


INVALID_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


def get_app_root() -> Path:
    """Return the directory used for runtime files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def ensure_runtime_directories() -> RuntimeDirectories:
    """Create the default logs, frames, and output directories."""
    app_root = get_app_root()
    log_dir = app_root / "logs"
    frames_dir = app_root / "frames"
    output_dir = app_root / "output"

    for directory in (log_dir, frames_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return RuntimeDirectories(
        app_root=app_root,
        log_dir=log_dir,
        frames_dir=frames_dir,
        output_dir=output_dir,
    )


def build_session_directory(frames_root: Path, started_at: datetime) -> Path:
    """Create a timestamped frame directory for one recording session."""
    session_dir = frames_root / started_at.strftime("%Y%m%d_%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def sanitize_file_name(value: str) -> str:
    """Replace characters that are illegal in Windows file names."""
    cleaned = INVALID_FILENAME_PATTERN.sub("_", value).strip().rstrip(".")
    return cleaned


def ensure_unique_video_path(candidate: Path) -> Path:
    """Prevent existing MP4 files from being overwritten."""
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent

    for counter in range(1, 10_000):
        alternative = parent / f"{stem}_{counter:02d}{suffix}"
        if not alternative.exists():
            return alternative

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return parent / f"{stem}_{timestamp}{suffix}"
