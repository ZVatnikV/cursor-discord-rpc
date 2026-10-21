"""HTML UI via pywebview."""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


def _web_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "src" / "web"
    return Path(__file__).resolve().parent / "web"


class Api:
    """JS bridge methods (called from app.js)."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_snapshot(self) -> dict[str, Any]:
        svc = self._service
        with svc._lock:
            cfg = dict(svc.cfg)
        state = svc.get_live_state()
        ok, msg = svc.get_rpc_status()

        # Build presence lines the same way Discord gets them
        from .rpc import DiscordRPC

        payload = DiscordRPC("0").build_presence(cfg, state)
        return {
            "config": {
                "enabled": bool(cfg.get("enabled", True)),
                "language": cfg.get("language") or "en",
                "show_elapsed": bool(cfg.get("show_elapsed", True)),
                "button_enabled": bool(cfg.get("button_enabled", True)),
                "autostart": bool(cfg.get("autostart", True)),
                "button_url": cfg.get("button_url") or "",
            },
            "live": {
                "running": bool(state.running),
                "activity": state.activity or "",
                "chat_name": state.chat_name or "",
                "workspace": state.workspace or "",
                "kind": state.kind or "idle",
                "details": payload.get("details") or "",
                "state": payload.get("state") or "",
            },
            "status": {"ok": ok, "msg": msg},
            "started_at": getattr(svc.rpc, "_start_ts", None) or int(time.time()),
        }

    def save_config(self, cfg: dict[str, Any]) -> dict[str, Any]:
        svc = self._service
        with svc._lock:
            merged = dict(svc.cfg)
        for key in (
            "language",
            "enabled",
            "show_elapsed",
            "button_enabled",
            "autostart",
        ):
            if key in cfg:
                merged[key] = cfg[key]
        svc.apply_config(merged)
        return {"ok": True}

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        self._service.set_enabled(bool(enabled))
        return {"ok": True, "enabled": bool(enabled)}


class WebUI:
    def __init__(
        self,
        service: Any,
        start_minimized: bool = False,
        on_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        self.service = service
        self.start_minimized = start_minimized
        self.on_ready = on_ready
        self._window = None
        self._api = Api(service)

    def show_window(self) -> None:
        if self._window is None:
            return
        try:
            self._window.restore()
            self._window.show()
            self._window.activate()
        except Exception as exc:
            log.warning("show_window: %s", exc)

    def set_enabled_ui(self, enabled: bool) -> None:
        # UI polls snapshot; nothing to push except ensure config saved
        self.service.set_enabled(enabled)

    def destroy_app(self) -> None:
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass

    def mainloop(self) -> None:
        import webview

        index = _web_dir() / "index.html"
        if not index.exists():
            raise FileNotFoundError(f"UI missing: {index}")

        self._window = webview.create_window(
            title="Cursor Discord RPC",
            url=index.as_uri(),
            js_api=self._api,
            width=520,
            height=720,
            min_size=(460, 640),
            background_color="#070b10",
            text_select=False,
        )

        def _on_closing() -> bool:
            # Hide to tray instead of quitting
            try:
                self._window.hide()
            except Exception:
                pass
            return False

        self._window.events.closing += _on_closing

        if self.on_ready:
            threading.Thread(target=self._deferred_ready, daemon=True).start()

        try:
            webview.start(gui="edgechromium", debug=False)
        except Exception as exc:
            log.warning("edgechromium unavailable (%s), falling back", exc)
            webview.start(debug=False)

    def _deferred_ready(self) -> None:
        time.sleep(0.35)
        if self.start_minimized and self._window is not None:
            try:
                self._window.hide()
            except Exception:
                pass
        if self.on_ready:
            self.on_ready()
