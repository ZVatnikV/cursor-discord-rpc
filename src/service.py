"""Background service: watch Cursor, push Discord presence, tray."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Optional

from . import autostart
from .config import APP_NAME, load_config, save_config
from .cursor_watcher import CursorWatcher
from .rpc_client import DiscordRPC

log = logging.getLogger(__name__)


class RPCService:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.watcher = CursorWatcher()
        self.rpc = DiscordRPC(str(self.cfg.get("discord_client_id") or ""))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status_ok = False
        self._status_msg = "Starting"
        self._lock = threading.Lock()
        self.app = None
        self._tray = None

    def get_live_state(self):
        return self.watcher.state

    def get_rpc_status(self) -> tuple[bool, str]:
        return self._status_ok, self._status_msg

    def apply_config(self, cfg: dict[str, Any]) -> None:
        with self._lock:
            old_id = str(self.cfg.get("discord_client_id") or "")
            was = bool(self.cfg.get("enabled", True))
            self.cfg = dict(cfg)
            save_config(self.cfg)
            new_id = str(self.cfg.get("discord_client_id") or "")
            if new_id != old_id:
                self.rpc.reconnect(new_id)
            if was and not self.cfg.get("enabled", True):
                self.rpc.clear()
                self._status_ok = False
                self._status_msg = "Disabled"
            autostart.sync_autostart(bool(self.cfg.get("autostart", True)))

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.cfg["enabled"] = bool(enabled)
            save_config(self.cfg)
            if not enabled:
                self.rpc.clear()
                self._status_ok = False
                self._status_msg = "Disabled"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        autostart.sync_autostart(bool(self.cfg.get("autostart", True)))
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="rpc-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.rpc.disconnect()
        except Exception:
            pass
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    cfg = dict(self.cfg)
                state = self.watcher.refresh()

                if not cfg.get("enabled", True):
                    self.rpc.clear()
                    self._status_ok = False
                    self._status_msg = "Disabled"
                elif cfg.get("only_when_cursor_running", True) and not state.running:
                    self.rpc.clear()
                    self._status_ok = False
                    self._status_msg = "Waiting Cursor"
                else:
                    ok = self.rpc.update(cfg, state)
                    self._status_ok = ok
                    self._status_msg = "Connected" if ok else "Discord offline"
            except Exception as exc:
                log.exception("loop: %s", exc)
                self._status_ok = False
                self._status_msg = "Error"
            self._stop.wait(2.0)

    def run_tray_and_ui(self, start_minimized: bool = False) -> None:
        from PIL import Image, ImageDraw

        from .ui.app import SettingsApp

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(61, 214, 198, 255))
        draw.rectangle((18, 22, 46, 42), outline=(7, 16, 24, 255), width=3)

        self.app = SettingsApp(
            config=self.cfg,
            on_save=self.apply_config,
            on_toggle_rpc=self.set_enabled,
            get_live_state=self.get_live_state,
            get_rpc_status=self.get_rpc_status,
            start_minimized=start_minimized or bool(self.cfg.get("start_minimized")),
        )
        self.start()

        def on_open(_i=None, _item=None):
            self.app.after(0, self.app.show_window)

        def on_off(_i=None, _item=None):
            self.set_enabled(False)
            self.app.after(0, lambda: self.app._set_enabled(False))

        def on_on(_i=None, _item=None):
            self.set_enabled(True)
            self.app.after(0, lambda: self.app._set_enabled(True))

        def on_quit(_i=None, _item=None):
            self.stop()
            self.app.after(0, self.app.destroy_app)

        try:
            import pystray
            from pystray import MenuItem as Item

            menu = pystray.Menu(
                Item("Настройки", on_open, default=True),
                Item("Отключить RPC", on_off),
                Item("Включить RPC", on_on),
                Item("Выход", on_quit),
            )
            self._tray = pystray.Icon("cursor_discord_rpc", img, APP_NAME, menu)
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception as exc:
            log.warning("Tray: %s", exc)

        self.app.mainloop()
        self.stop()


def configure_logging() -> None:
    from .config import CONFIG_DIR, ensure_config_dir

    ensure_config_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(CONFIG_DIR / "app.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
