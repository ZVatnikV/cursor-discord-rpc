"""Single-instance lock."""

from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

LOCK_PATH = Path.home() / ".cursor-discord-rpc" / "app.lock"


def _pid_alive(pid: int) -> bool:
    if psutil is None:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    return psutil.pid_exists(pid)


def kill_other_instances() -> int:
    if psutil is None:
        return 0
    me = os.getpid()
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            pid = proc.info["pid"]
            if pid == me:
                continue
            name = (proc.info.get("name") or "").lower().replace(" ", "")
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            exe = (proc.info.get("exe") or "").lower()
            is_rpc = (
                "cursordiscordrpc" in name
                or "cursordiscordrpc" in exe
                or ("run.py" in cmdline and "discord" in cmdline and "rpc" in cmdline)
            )
            if is_rpc:
                proc.kill()
                killed += 1
        except (psutil.Error, OSError):
            continue
    return killed


def acquire_lock() -> bool:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            old = int(LOCK_PATH.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            old = 0
        if old and old != os.getpid() and _pid_alive(old):
            return False
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")

    def _release() -> None:
        try:
            if LOCK_PATH.exists() and LOCK_PATH.read_text(encoding="utf-8").strip() == str(
                os.getpid()
            ):
                LOCK_PATH.unlink()
        except OSError:
            pass

    atexit.register(_release)
    return True
