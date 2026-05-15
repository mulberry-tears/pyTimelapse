"""FFmpeg integration for timelapse export."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from core.models import EncoderType, RecorderSettings
from utils.windows import find_bundled_ffmpeg, find_winget_ffmpeg


class FFmpegEncoder:
    """Build and execute FFmpeg commands for final timelapse export."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("timelapse.ffmpeg")

    def encode(
        self,
        frames_directory: Path,
        output_path: Path,
        settings: RecorderSettings,
    ) -> Path:
        """Encode captured JPEG frames into a single MP4 video."""
        frame_paths = sorted(frames_directory.glob("*.jpg"))
        if not frame_paths:
            raise RuntimeError("No JPEG frames were found for FFmpeg to encode.")

        ffmpeg_command = self._resolve_ffmpeg_command(settings.ffmpeg_path)

        sequence_dir = frames_directory / "_sequence"
        sequence_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._prepare_sequence_directory(frame_paths, sequence_dir)
            command = self._build_command(
                ffmpeg_binary=ffmpeg_command,
                sequence_dir=sequence_dir,
                output_path=output_path,
                settings=settings,
            )
            self._logger.debug("Running FFmpeg command: %s", " ".join(command))
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.stdout:
                self._logger.debug("FFmpeg stdout: %s", result.stdout.strip())
            if result.stderr:
                self._logger.error("FFmpeg stderr: %s", result.stderr.strip())

            if result.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg exited with code {result.returncode}. See logs/error.log for details."
                )

            return output_path
        finally:
            shutil.rmtree(sequence_dir, ignore_errors=True)

    def _resolve_ffmpeg_command(self, ffmpeg_path: Path) -> str:
        command = str(ffmpeg_path).strip()
        if not command:
            command = "ffmpeg"

        if ffmpeg_path.exists() and ffmpeg_path.is_file():
            return command

        discovered = shutil.which(command)
        if discovered:
            return discovered

        bundled_ffmpeg = find_bundled_ffmpeg()
        if bundled_ffmpeg is not None:
            return str(bundled_ffmpeg)

        winget_ffmpeg = find_winget_ffmpeg()
        if winget_ffmpeg is not None:
            return str(winget_ffmpeg)

        raise FileNotFoundError(f"FFmpeg executable was not found: {ffmpeg_path}")

    @staticmethod
    def is_available(ffmpeg_path: Path) -> bool:
        """Return whether an FFmpeg executable can be resolved."""
        command = str(ffmpeg_path).strip()
        if not command:
            command = "ffmpeg"

        return (
            (ffmpeg_path.exists() and ffmpeg_path.is_file())
            or shutil.which(command) is not None
            or find_bundled_ffmpeg() is not None
            or find_winget_ffmpeg() is not None
        )

    def _prepare_sequence_directory(self, frame_paths: list[Path], sequence_dir: Path) -> None:
        for index, frame_path in enumerate(frame_paths, start=1):
            target = sequence_dir / f"{index:06d}.jpg"
            try:
                os.link(frame_path, target)
            except OSError:
                shutil.copy2(frame_path, target)

    def _build_command(
        self,
        ffmpeg_binary: str,
        sequence_dir: Path,
        output_path: Path,
        settings: RecorderSettings,
    ) -> list[str]:
        codec_args = self._codec_arguments(settings.encoder, settings.crf)

        return [
            ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(settings.output_fps),
            "-i",
            str(sequence_dir / "%06d.jpg"),
            *codec_args,
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]

    def _codec_arguments(self, encoder: EncoderType, crf: int) -> list[str]:
        if encoder == EncoderType.H264:
            return ["-c:v", encoder.ffmpeg_codec, "-preset", "medium", "-crf", str(crf)]
        if encoder == EncoderType.H265:
            return ["-c:v", encoder.ffmpeg_codec, "-preset", "medium", "-crf", str(crf)]
        if encoder == EncoderType.H264_NVENC:
            return [
                "-c:v",
                encoder.ffmpeg_codec,
                "-preset",
                "p5",
                "-rc",
                "vbr",
                "-cq",
                str(crf),
                "-b:v",
                "0",
            ]
        if encoder == EncoderType.H265_NVENC:
            return [
                "-c:v",
                encoder.ffmpeg_codec,
                "-preset",
                "p5",
                "-rc",
                "vbr",
                "-cq",
                str(crf),
                "-b:v",
                "0",
            ]
        raise ValueError(f"Unsupported encoder: {encoder}")
