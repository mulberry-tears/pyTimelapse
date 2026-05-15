# pyTimelapse

`pyTimelapse` is a Windows desktop timelapse screen recorder built with Python, PySide6, `dxcam`, OpenCV, and FFmpeg. It captures the screen at a configurable interval, stores each frame as JPEG, and encodes the final result as an MP4 video.

This project is intended for long-running desktop capture scenarios such as workflow recording, software demonstrations, build progress tracking, and visual documentation.

## Features

- Native Windows desktop GUI built with PySide6
- Per-monitor capture with automatic display enumeration
- Configurable capture interval, output FPS, JPEG quality, and output filename
- FFmpeg-based MP4 export with support for:
  - `H.264 (libx264)`
  - `H.265 (libx265)`
  - `H.264 (NVENC)`
  - `H.265 (NVENC)`
- Timestamped frame session directories for each recording
- Automatic output filename deduplication to avoid overwriting existing videos
- Runtime CPU and memory monitoring in the GUI
- Application and error logging under `logs/`

## System Requirements

- Windows 11
- Python 3.12 or newer
- FFmpeg available in `PATH`, installed via `winget`, or selected manually in the GUI
- NVIDIA GPU with NVENC support if hardware encoding is required

## Dependencies

Core Python dependencies:

- `PySide6`
- `dxcam`
- `opencv-python`
- `psutil`

Install them with:

```powershell
pip install -r requirements.txt
```

## Installation

1. Clone this repository.
2. Create and activate a Python virtual environment.
3. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

4. Install FFmpeg.

## Installing FFmpeg

### Option 1: Install via winget

```powershell
winget install Gyan.FFmpeg
```

After installation, restart the terminal or sign out and back in if `PATH` has not refreshed yet.

### Option 2: Manual installation

1. Download a Windows FFmpeg build.
2. Extract it to a fixed location such as `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to the system `PATH`.
4. Verify the installation:

```powershell
ffmpeg -version
```

### Option 3: Select `ffmpeg.exe` in the GUI

If FFmpeg is not available in `PATH`, the application also allows selecting the executable manually.

## Running the Application

```powershell
python main.py
```

## Building an Executable

Install PyInstaller in the active virtual environment:

```powershell
python -m pip install pyinstaller
```

Build the Windows executable:

```powershell
python -m PyInstaller --noconfirm --clean pyTimelapse.spec
```

The packaged app is created at:

```text
dist/pyTimelapse/pyTimelapse.exe
```

The build bundles `ffmpeg.exe` automatically when it is available in `PATH`.

## Usage

1. Select the target display.
2. Set the capture interval in seconds.
3. Set the output FPS for the final MP4.
4. Set JPEG quality.
5. Choose a codec.
6. Adjust `CRF / CQ`:
   - For `libx264` / `libx265`, this maps to FFmpeg `-crf`.
   - For NVENC, this maps to FFmpeg `-cq`.
7. Set the output filename and destination directory.
8. Confirm the FFmpeg executable path if needed.
9. Start recording.
10. Stop recording when capture is complete. The application will then encode the saved frames into an MP4 file.

## Output Layout

Default runtime directories:

```text
logs/
frames/
output/
```

Each recording session creates a timestamped frame directory:

```text
frames/20260513_081530/
```

Saved frame filenames follow this pattern:

```text
000001_20260513_081530.jpg
000002_20260513_081535.jpg
```

Encoded videos are written to `output/` by default unless another directory is selected in the GUI.

## Project Structure

```text
pyTimelapse/
+-- main.py
+-- core/
|   +-- capture_service.py
|   +-- models.py
|   `-- system_monitor.py
+-- ffmpeg/
|   `-- encoder.py
+-- gui/
|   `-- main_window.py
+-- utils/
|   +-- logging_config.py
|   +-- paths.py
|   `-- windows.py
+-- frames/
+-- logs/
+-- output/
+-- requirements.txt
`-- README.md
```

## Encoding Notes

- `H.264` is the most broadly compatible output format.
- `H.265` usually provides better compression efficiency, but playback compatibility can be narrower.
- NVENC reduces CPU load during encoding, but requires a compatible NVIDIA GPU and an FFmpeg build with NVENC enabled.
- The application preserves captured JPEG frames, which is useful for debugging, re-encoding, or post-processing.

## Troubleshooting

### `ModuleNotFoundError`

Install dependencies again inside the active virtual environment:

```powershell
pip install -r requirements.txt
```

### `FFmpeg executable was not found`

Check the following:

- `ffmpeg.exe` is installed correctly
- FFmpeg is available in `PATH`
- The path configured in the GUI points to a valid executable

### NVENC codecs are unavailable

Verify that:

- The system has a supported NVIDIA GPU
- GPU drivers are installed correctly
- The FFmpeg build includes NVENC support

You can verify encoder availability with:

```powershell
ffmpeg -encoders | findstr nvenc
```

### Encoding failed

Review:

- `logs/error.log`
- `logs/debug.log`

These logs usually contain the FFmpeg error output and runtime context needed for diagnosis.

## Practical Recommendations

- For long-duration recording, start with a capture interval between `3` and `10` seconds.
- A JPEG quality value between `80` and `90` is usually a reasonable balance between disk usage and image quality.
- If storage is limited, lower the output FPS or increase the capture interval.
- For general-purpose output, `H.264` with a `CRF / CQ` value around `22` to `26` is a practical default range.

## Current Scope

This project currently focuses on:

- Windows desktop capture
- Single-session GUI-based operation
- Timelapse export to MP4 through FFmpeg

Planned or possible future improvements may include:

- pause/resume support
- automatic cleanup of old frame directories
- additional output formats
- richer session history and export management
