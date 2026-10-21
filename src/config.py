"""Persistent settings."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_NAME = "Cursor Discord RPC"
APP_VERSION = "2.0.0"

# Kept from the previous app
DISCORD_CLIENT_ID = "1562085628630540318"
REPO_URL = "https://github.com/ZVatnikV/cursor-discord-rpc"

CONFIG_DIR = Path.home() / ".cursor-discord-rpc"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "discord_client_id": DISCORD_CLIENT_ID,
    "enabled": True,
    "show_elapsed": True,
    "button_enabled": True,
    "button_label": "GitHub",
    "button_url": REPO_URL,
    "autostart": True,
    "only_when_cursor_running": True,
    "start_minimized": False,
    "large_image_key": "cursor",
}


def ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_config() -> dict[str, Any]:
    ensure_config_dir()
    cfg = deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update({k: v for k, v in raw.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass
    if not cfg.get("discord_client_id"):
        cfg["discord_client_id"] = DISCORD_CLIENT_ID
    if not cfg.get("button_url"):
        cfg["button_url"] = REPO_URL
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    ensure_config_dir()
    merged = deepcopy(DEFAULTS)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    CONFIG_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
