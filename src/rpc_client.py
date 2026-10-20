"""Discord Rich Presence — official fields only: details + state (+ buttons)."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .config import REPO_URL
from .cursor_watcher import CursorState

log = logging.getLogger(__name__)
FORCE_REFRESH_SEC = 12


def _clip(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: max(0, n - 1)].rstrip() + "…"


class DiscordRPC:
    def __init__(self, client_id: str) -> None:
        self.client_id = str(client_id or "").strip()
        self._rpc = None
        self._connected = False
        self._start_ts: Optional[int] = None
        self._last_payload: dict[str, Any] = {}
        self._last_push = 0.0
        self._skip_image = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        if not self.client_id:
            return False
        try:
            from pypresence import Presence

            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            self._start_ts = int(time.time())
            self._last_payload = {}
            self._last_push = 0.0
            log.info("Connected Discord RPC %s", self.client_id)
            return True
        except Exception as exc:
            log.warning("RPC connect failed: %s", exc)
            self._connected = False
            self._rpc = None
            return False

    def disconnect(self) -> None:
        if self._rpc is not None:
            try:
                self._rpc.clear()
            except Exception:
                pass
            try:
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
        self._connected = False
        self._last_payload = {}
        self._last_push = 0.0

    def reconnect(self, client_id: str) -> bool:
        self.disconnect()
        self.client_id = str(client_id or "").strip()
        self._skip_image = False
        return self.connect()

    def clear(self) -> None:
        if self._rpc and self._connected:
            try:
                self._rpc.clear()
            except Exception:
                pass
        self._last_payload = {}
        self._last_push = 0.0

    def build_presence(self, cfg: dict[str, Any], state: CursorState) -> dict[str, Any]:
        """
        Discord allows only TWO text lines (docs.discord.com):
          details = what you're doing
          state   = context (chat / project)
        Buttons exist but YOU cannot see them — only others.
        """
        activity = state.activity_label or "В Cursor"
        file_name = state.file_name if cfg.get("show_file", True) else ""
        workspace = state.workspace if cfg.get("show_workspace", True) else ""
        chat = ""
        if cfg.get("show_chat", True):
            chat = (cfg.get("manual_chat_name") or "").strip() or state.chat_name

        # Line 1: activity + file
        if file_name:
            details = _clip(f"{activity} · {file_name}", 128)
        else:
            details = _clip(activity, 128)

        # Line 2: chat first (what user asked for), then project
        if chat and workspace:
            state_text = _clip(f"{chat} · {workspace}", 128)
        elif chat:
            state_text = _clip(chat, 128)
        elif workspace:
            state_text = _clip(workspace, 128)
        else:
            state_text = "Cursor IDE"

        payload: dict[str, Any] = {
            "details": details,
            "state": state_text,
        }

        if not self._skip_image:
            payload["large_image"] = cfg.get("large_image_key") or "cursor"
            payload["large_text"] = _clip(workspace or "Cursor IDE", 128)

        if cfg.get("show_elapsed", True):
            if self._start_ts is None:
                self._start_ts = int(time.time())
            payload["start"] = self._start_ts

        if cfg.get("button_enabled", True):
            label = (cfg.get("button_label") or "GitHub").strip()[:32] or "GitHub"
            url = (cfg.get("button_url") or REPO_URL).strip()
            if not url.startswith("http"):
                url = REPO_URL
            payload["buttons"] = [{"label": label, "url": url}]

        return payload

    def update(self, cfg: dict[str, Any], state: CursorState) -> bool:
        if not self._connected or self._rpc is None:
            if not self.connect():
                return False

        payload = self.build_presence(cfg, state)
        now = time.time()
        stale = (now - self._last_push) >= FORCE_REFRESH_SEC
        if payload == self._last_payload and not stale:
            return True

        try:
            self._rpc.update(**payload)
            self._last_payload = payload
            self._last_push = now
            log.info("RPC → %r | %r", payload.get("details"), payload.get("state"))
            return True
        except Exception as exc:
            log.warning("RPC update failed: %s", exc)
            if "large_image" in payload and not self._skip_image:
                self._skip_image = True
                self._last_payload = {}
                try:
                    p2 = self.build_presence(cfg, state)
                    self._rpc.update(**p2)
                    self._last_payload = p2
                    self._last_push = now
                    return True
                except Exception as exc2:
                    log.warning("RPC retry failed: %s", exc2)
            self._connected = False
            self._last_payload = {}
            return False
