"""Windows Startup shortcut."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "Cursor Discord RPC.lnk"


def _startup_folder() -> Path:
    return (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def enable_autostart() -> bool:
    startup = _startup_folder()
    startup.mkdir(parents=True, exist_ok=True)
    shortcut = startup / SHORTCUT_NAME

    if getattr(sys, "frozen", False):
        target = sys.executable
        workdir = str(Path(sys.executable).parent)
        args = "--minimized"
        ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{shortcut}')
$s.TargetPath = '{target}'
$s.Arguments = '{args}'
$s.WorkingDirectory = '{workdir}'
$s.WindowStyle = 7
$s.Description = 'Cursor Discord RPC'
$s.Save()
"""
    else:
        python = sys.executable
        script = str(Path(__file__).resolve().parent.parent / "run.py")
        workdir = str(Path(__file__).resolve().parent.parent)
        ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{shortcut}')
$s.TargetPath = '{python}'
$s.Arguments = '"{script}" --minimized'
$s.WorkingDirectory = '{workdir}'
$s.WindowStyle = 7
$s.Description = 'Cursor Discord RPC'
$s.Save()
"""

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True,
            capture_output=True,
            text=True,
        )
        return shortcut.exists()
    except (subprocess.CalledProcessError, OSError):
        return False


def disable_autostart() -> bool:
    shortcut = _startup_folder() / SHORTCUT_NAME
    try:
        if shortcut.exists():
            shortcut.unlink()
        return True
    except OSError:
        return False


def sync_autostart(enabled: bool) -> bool:
    return enable_autostart() if enabled else disable_autostart()
