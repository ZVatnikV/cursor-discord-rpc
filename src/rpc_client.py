"""Discord Rich Presence client wrapper."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .config import ACTIVITY_PRESETS, REPO_URL
from .cursor_watcher import CursorState

log = logging.getLogger(__name__)


class DiscordRPC:
    def __init__(self, client_id: str) -> None:
        self.client_id = str(client_id or "").strip()
        self._rpc = None
        self._connected = False
        self._start_ts: Optional[int] = None
        self._last_payload: dict[str, Any] = {}
        self._skip_image = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        if not self.client_id:
            log.warning("Discord RPC connect failed: empty Client ID")
            self._connected = False
            return False
        try:
            from pypresence import Presence

            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            self._start_ts = int(time.time())
            log.info("Connected to Discord RPC as %s", self.client_id)
            return True
        except Exception as exc:
            log.warning("Discord RPC connect failed: %s", exc)
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

    def build_presence(
        self,
        cfg: dict[str, Any],
        state: CursorState,
    ) -> dict[str, Any]:
        activity_mode = cfg.get("activity_mode", "auto")
        if activity_mode == "auto":
            activity_text = state.activity_label
        elif activity_mode == "custom":
            activity_text = (cfg.get("custom_activity") or "В Cursor").strip()
        else:
            activity_text = ACTIVITY_PRESETS.get(activity_mode, activity_mode)

        details_parts: list[str] = []
        state_parts: list[str] = []

        custom_details = (cfg.get("custom_details") or "").strip()
        custom_state = (cfg.get("custom_state") or "").strip()

        if custom_details:
            details_parts.append(custom_details)
        elif cfg.get("show_activity", True):
            details_parts.append(activity_text)

        if custom_state:
            state_parts.append(custom_state)
        else:
            if cfg.get("show_file", True) and state.file_name:
                state_parts.append(state.file_name)
            if cfg.get("show_workspace", True) and state.workspace:
                if state.file_name and cfg.get("show_file", True):
                    state_parts.append(f"в {state.workspace}")
                else:
                    state_parts.append(state.workspace)
            if cfg.get("show_chat", True):
                chat = (cfg.get("manual_chat_name") or "").strip() or state.chat_name
                if chat:
                    state_parts.append(f"чат: {chat}")

        details = " · ".join(details_parts)[:128] or "Cursor IDE"
        state_text = " · ".join(state_parts)[:128] or "Coding"

        payload: dict[str, Any] = {
            "details": details,
            "state": state_text,
        }

        if not self._skip_image:
            payload["large_image"] = cfg.get("large_image_key") or "cursor"
            payload["large_text"] = cfg.get("large_image_text") or "Cursor IDE"

        if cfg.get("show_elapsed", True):
            if self._start_ts is None:
                self._start_ts = int(time.time())
            payload["start"] = self._start_ts

        if cfg.get("button_enabled", True):
            label = (cfg.get("button_label") or "GitHub").strip()[:32] or "GitHub"
            url = (cfg.get("button_url") or REPO_URL).strip()
            if not url.startswith("http"):
                url = REPO_URL
            # Discord allows max 2 buttons; label 1–32 chars
            payload["buttons"] = [{"label": label, "url": url}]

        return payload

    def update(self, cfg: dict[str, Any], state: CursorState) -> bool:
        if not self._connected or self._rpc is None:
            if not self.connect():
                return False

        payload = self.build_presence(cfg, state)
        if payload == self._last_payload:
            return True

        try:
            self._rpc.update(**payload)
            self._last_payload = payload
            log.info(
                "RPC updated details=%r state=%r buttons=%s",
                payload.get("details"),
                payload.get("state"),
                bool(payload.get("buttons")),
            )
            return True
        except Exception as exc:
            log.warning("RPC update failed: %s | payload keys=%s", exc, list(payload))
            # Missing art asset often breaks the whole activity — retry without image
            if "large_image" in payload and not self._skip_image:
                self._skip_image = True
                self._last_payload = {}
                try:
                    payload2 = self.build_presence(cfg, state)
                    self._rpc.update(**payload2)
                    self._last_payload = payload2
                    log.info("RPC updated without large_image")
                    return True
                except Exception as exc2:
                    log.warning("RPC retry failed: %s", exc2)
            self._connected = False
            self._last_payload = {}
            return False
