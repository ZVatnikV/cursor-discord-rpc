"""Minimal persistent settings."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_NAME = "Cursor Discord RPC"
APP_VERSION = "1.2.1"
REPO_URL = "https://github.com/ItzHanchik/cursor-discord-rpc"
DISCORD_CLIENT_ID_DEFAULT = "1562085628630540318"

CONFIG_DIR = Path.home() / ".cursor-discord-rpc"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "discord_client_id": DISCORD_CLIENT_ID_DEFAULT,
    "enabled": True,
    "show_file": True,
    "show_workspace": True,
    "show_chat": True,
    "show_elapsed": True,
    "button_enabled": True,
    "button_label": "GitHub",
    "button_url": REPO_URL,
    "autostart": True,
    "only_when_cursor_running": True,
    "start_minimized": False,
    "large_image_key": "cursor",
    "manual_chat_name": "",
}


def ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_config() -> dict[str, Any]:
    ensure_config_dir()
    cfg = deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update({k: v for k, v in raw.items() if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError):
            pass
    if not cfg.get("discord_client_id"):
        cfg["discord_client_id"] = DISCORD_CLIENT_ID_DEFAULT
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    ensure_config_dir()
    merged = deepcopy(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_CONFIG})
    CONFIG_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
