#!/usr/bin/env python3
"""Entry point — python run.py [--minimized]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path when frozen/dev
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

    configure_logging()
    service = RPCService()
    service.run_tray_and_ui(start_minimized=args.minimized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
