"""Compact Cursor-style settings window."""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from .config import APP_NAME, APP_VERSION, REPO_URL, save_config
from .rpc import DiscordRPC
from .watcher import CursorState

COLORS = {
    "bg": "#0b0f14",
    "surface": "#121821",
    "border": "#243041",
    "text": "#e8eef6",
    "muted": "#8b9bb0",
    "accent": "#3dd6c6",
    "accent_hover": "#5ee6d6",
    "danger": "#e85d5d",
    "ok": "#4ecf8a",
}

FONTS = {
    "title": ("Segoe UI Semibold", 22),
    "heading": ("Segoe UI Semibold", 14),
    "body": ("Segoe UI", 13),
    "small": ("Segoe UI", 11),
}


class SettingsApp(ctk.CTk):
    def __init__(
        self,
        config: dict[str, Any],
        on_save: Optional[Callable[[dict[str, Any]], None]] = None,
        on_toggle_rpc: Optional[Callable[[bool], None]] = None,
        get_live_state: Optional[Callable[[], CursorState]] = None,
        get_rpc_status: Optional[Callable[[], tuple[bool, str]]] = None,
        start_minimized: bool = False,
    ) -> None:
        super().__init__()
        self.cfg = dict(config)
        self.on_save = on_save
        self.on_toggle_rpc = on_toggle_rpc
        self.get_live_state = get_live_state
        self.get_rpc_status = get_rpc_status
        self._vars: dict[str, Any] = {}
        self._closing = False

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(APP_NAME)
        self.geometry("480x520")
        self.minsize(440, 480)
        self.configure(fg_color=COLORS["bg"])

        self._build()
        self._load()
        self.after(500, self._tick)
        if start_minimized:
            self.withdraw()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        root = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        root.pack(fill="both", expand=True, padx=22, pady=22)

        top = ctk.CTkFrame(root, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top, text=APP_NAME, font=FONTS["title"], text_color=COLORS["text"], anchor="w"
        ).pack(side="left")
        self.status_pill = ctk.CTkLabel(
            top,
            text="○ Offline",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            fg_color=COLORS["surface"],
            corner_radius=999,
            padx=10,
            pady=5,
        )
        self.status_pill.pack(side="right")

        ctk.CTkLabel(
            root,
            text=f"Rich Presence для Cursor · v{APP_VERSION}",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(4, 16))

        card = ctk.CTkFrame(
            root,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x")

        self.power_btn = ctk.CTkButton(
            card,
            text="Отключить RPC",
            font=FONTS["heading"],
            fg_color=COLORS["danger"],
            hover_color="#c44a4a",
            text_color="#fff",
            height=42,
            corner_radius=10,
            command=self._toggle,
        )
        self.power_btn.pack(fill="x", padx=16, pady=(16, 10))

        for key, label in (
            ("show_elapsed", "Таймер сессии"),
            ("button_enabled", "Кнопка GitHub (видят друзья)"),
            ("autostart", "Автозапуск с Windows"),
        ):
            self._switch(card, key, label)

        ctk.CTkLabel(
            card,
            text="details — что делает AI · state — чат · workspace",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(8, 16))

        prev = ctk.CTkFrame(
            root,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        prev.pack(fill="both", expand=True, pady=(14, 0))

        ctk.CTkLabel(
            prev,
            text="Превью Discord",
            font=FONTS["heading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 8))

        self.preview_details = ctk.CTkLabel(
            prev, text="…", font=FONTS["heading"], text_color=COLORS["text"], anchor="w"
        )
        self.preview_details.pack(fill="x", padx=16)

        self.preview_state = ctk.CTkLabel(
            prev,
            text="…",
            font=FONTS["body"],
            text_color=COLORS["muted"],
            anchor="w",
            wraplength=400,
            justify="left",
        )
        self.preview_state.pack(fill="x", padx=16, pady=(2, 4))

        self.live_label = ctk.CTkLabel(
            prev,
            text="",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.live_label.pack(fill="x", padx=16, pady=(8, 16))

        foot = ctk.CTkFrame(root, fg_color="transparent")
        foot.pack(fill="x", pady=(12, 0))
        self.toast = ctk.CTkLabel(
            foot, text="", font=FONTS["small"], text_color=COLORS["accent"], anchor="w"
        )
        self.toast.pack(side="left")
        ctk.CTkButton(
            foot,
            text="Сохранить",
            font=FONTS["heading"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#071018",
            height=38,
            width=120,
            corner_radius=10,
            command=self._save,
        ).pack(side="right")

        self._sync_power()

    def _switch(self, parent, key: str, label: str) -> None:
        var = ctk.BooleanVar(value=bool(self.cfg.get(key, False)))
        self._vars[key] = var
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        ctk.CTkLabel(
            row, text=label, font=FONTS["body"], text_color=COLORS["text"], anchor="w"
        ).pack(side="left")
        ctk.CTkSwitch(
            row,
            text="",
            variable=var,
            progress_color=COLORS["accent"],
            command=self._preview,
        ).pack(side="right")

    def _load(self) -> None:
        for k, var in self._vars.items():
            if k in self.cfg:
                var.set(bool(self.cfg[k]))

    def _collect(self) -> dict[str, Any]:
        out = dict(self.cfg)
        for k, var in self._vars.items():
            out[k] = bool(var.get())
        out.setdefault("button_url", REPO_URL)
        out.setdefault("button_label", "GitHub")
        return out

    def _sync_power(self) -> None:
        on = bool(self.cfg.get("enabled", True))
        if on:
            self.power_btn.configure(
                text="Отключить RPC", fg_color=COLORS["danger"], hover_color="#c44a4a"
            )
        else:
            self.power_btn.configure(
                text="Включить RPC", fg_color=COLORS["ok"], hover_color="#3db872"
            )

    def _toggle(self) -> None:
        self.set_enabled_ui(not bool(self.cfg.get("enabled", True)))

    def set_enabled_ui(self, enabled: bool) -> None:
        self.cfg["enabled"] = enabled
        self.cfg = self._collect()
        self.cfg["enabled"] = enabled
        save_config(self.cfg)
        if self.on_toggle_rpc:
            self.on_toggle_rpc(enabled)
        elif self.on_save:
            self.on_save(self.cfg)
        self._sync_power()
        self._preview()
        self._flash("RPC выключен" if not enabled else "RPC включён")

    def _save(self) -> None:
        enabled = bool(self.cfg.get("enabled", True))
        self.cfg = self._collect()
        self.cfg["enabled"] = enabled
        save_config(self.cfg)
        if self.on_save:
            self.on_save(self.cfg)
        self._flash("Сохранено")
        self._preview()

    def _flash(self, text: str) -> None:
        self.toast.configure(text=text)
        self.after(2000, lambda: self.toast.configure(text=""))

    def _preview(self) -> None:
        cfg = self._collect()
        cfg["enabled"] = bool(self.cfg.get("enabled", True))
        state = CursorState(
            running=True,
            workspace="cursor-discord-rpc",
            chat_name="Настройка RPC",
            activity="Редактирует ui.py",
        )
        if self.get_live_state:
            live = self.get_live_state()
            if live.workspace:
                state.workspace = live.workspace
            if live.chat_name:
                state.chat_name = live.chat_name
            if live.activity:
                state.activity = live.activity

        if not cfg.get("enabled", True):
            self.preview_details.configure(text="RPC выключен")
            self.preview_state.configure(text="")
            return

        payload = DiscordRPC("0").build_presence(cfg, state)
        self.preview_details.configure(text=payload.get("details", ""))
        self.preview_state.configure(text=payload.get("state", ""))

    def _tick(self) -> None:
        if self._closing:
            return
        try:
            self._preview()
            if self.get_live_state:
                s = self.get_live_state()
                self.live_label.configure(
                    text=(
                        f"{'● Cursor' if s.running else '○ Cursor offline'}\n"
                        f"AI: {s.activity or '—'}\n"
                        f"Чат: {s.chat_name or '—'}\n"
                        f"Workspace: {s.workspace or '—'}"
                    )
                )
            if self.get_rpc_status:
                ok, msg = self.get_rpc_status()
                self.status_pill.configure(
                    text=f"{'●' if ok else '○'} {msg}",
                    text_color=COLORS["ok"] if ok else COLORS["muted"],
                )
        except Exception:
            pass
        self.after(1200, self._tick)

    def _on_close(self) -> None:
        self.withdraw()

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def destroy_app(self) -> None:
        self._closing = True
        self.destroy()
