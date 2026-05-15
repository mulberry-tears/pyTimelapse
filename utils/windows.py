"""Windows-specific helpers."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from core.models import ScreenInfo


class RECT(ctypes.Structure):
    """RECT structure for monitor enumeration."""

    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    """Monitor info structure including the device name."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def set_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness when available."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            return


def enumerate_monitors() -> list[ScreenInfo]:
    """Return monitors in the order reported by Windows."""
    user32 = ctypes.windll.user32
    monitors: list[ScreenInfo] = []

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def callback(
        monitor_handle: wintypes.HMONITOR,
        _device_context: wintypes.HDC,
        _rect: ctypes.POINTER(RECT),
        _data: wintypes.LPARAM,
    ) -> bool:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not user32.GetMonitorInfoW(monitor_handle, ctypes.byref(info)):
            return True

        width = info.rcMonitor.right - info.rcMonitor.left
        height = info.rcMonitor.bottom - info.rcMonitor.top
        is_primary = bool(info.dwFlags & 1)
        index = len(monitors)
        label = f"Display {index + 1} | {width}x{height}"
        if is_primary:
            label += " | Primary"
        label += f" | {info.szDevice}"

        monitors.append(
            ScreenInfo(
                index=index,
                label=label,
                width=width,
                height=height,
                is_primary=is_primary,
                device_name=info.szDevice,
            )
        )
        return True

    if not user32.EnumDisplayMonitors(None, None, monitor_enum_proc(callback), 0):
        return []

    return monitors


def find_winget_ffmpeg() -> Path | None:
    """Locate ffmpeg.exe from a winget installation when PATH is not refreshed yet."""
    package_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if not package_root.exists():
        return None

    matches = sorted(package_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
    if not matches:
        return None

    return matches[-1]


def find_bundled_ffmpeg() -> Path | None:
    """Locate ffmpeg.exe bundled beside a frozen executable."""
    if not getattr(sys, "frozen", False):
        return None

    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        executable_dir / "ffmpeg.exe",
        executable_dir / "_internal" / "ffmpeg.exe",
    ]

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "ffmpeg.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None
