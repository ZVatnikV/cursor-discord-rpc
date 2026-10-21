"""Discord Rich Presence client."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .config import REPO_URL
from .watcher import CursorState

log = logging.getLogger(__name__)
MIN_PUSH_SEC = 2.0


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
        self._tick = 0

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
            log.info("Discord RPC connected (%s)", self.client_id)
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

    def clear(self) -> None:
        if self._rpc and self._connected:
            try:
                self._rpc.clear()
            except Exception:
                pass
        self._last_payload = {}
        self._last_push = 0.0

    def build_presence(self, cfg: dict[str, Any], state: CursorState) -> dict[str, Any]:
        # Line 1 — what the AI is doing in the active chat
        details = _clip(state.activity or "В Cursor", 128)

        # Line 2 — chat name · workspace
        chat = (state.chat_name or "").strip()
        workspace = (state.workspace or "").strip()
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
        content = (payload.get("details"), payload.get("state"))
        last = (self._last_payload.get("details"), self._last_payload.get("state"))
        if content == last and (now - self._last_push) < MIN_PUSH_SEC:
            return True

        try:
            self._rpc.update(**payload)
            self._last_payload = payload
            self._last_push = now
            self._tick += 1
            log.info("RPC #%s → %r | %r", self._tick, payload.get("details"), payload.get("state"))
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
