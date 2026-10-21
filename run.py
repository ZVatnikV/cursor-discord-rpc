#!/usr/bin/env python3
"""Cursor Discord RPC — entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Cursor Discord RPC")
    parser.add_argument("--minimized", action="store_true", help="Start in tray")
    args = parser.parse_args()

    from src.instance import acquire_lock, kill_other_instances
    from src.service import RPCService, configure_logging

    configure_logging()
    killed = kill_other_instances()
    if killed:
        print(f"Stopped {killed} old instance(s)")
    if not acquire_lock():
        print("Already running")
        return 0

    RPCService().run(start_minimized=args.minimized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
