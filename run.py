#!/usr/bin/env python3
"""Entry point — python run.py [--minimized]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Cursor Discord RPC")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start hidden in the system tray",
    )
    args = parser.parse_args()

    from src.service import RPCService, configure_logging
    from src.single_instance import acquire_lock, kill_other_instances

    configure_logging()
    killed = kill_other_instances()
    if killed:
        print(f"Killed {killed} old RPC instance(s)")
    if not acquire_lock():
        # Another copy just won the race — exit quietly
        print("Already running")
        return 0

    service = RPCService()
    service.run_tray_and_ui(start_minimized=args.minimized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
