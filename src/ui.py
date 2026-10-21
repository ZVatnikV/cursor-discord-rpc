"""Animated Cursor-style settings window (EN default / RU)."""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

import customtkinter as ctk

from .config import APP_NAME, APP_VERSION, REPO_URL, save_config
from .i18n import normalize_lang, t
from .rpc import DiscordRPC
from .watcher import CursorState

COLORS = {
    "bg": "#080c11",
    "bg2": "#0d131a",
    "surface": "#121a24",
    "surface2": "#182230",
    "border": "#243041",
    "border_hot": "#3a5168",
    "text": "#e8eef6",
    "muted": "#8b9bb0",
    "accent": "#3dd6c6",
    "accent_dim": "#1fa896",
    "accent_hover": "#5ee6d6",
    "danger": "#e85d5d",
    "danger_hover": "#c44a4a",
    "ok": "#4ecf8a",
    "ok_hover": "#3db872",
    "discord": "#5865f2",
}

FONTS = {
    "brand": ("Segoe UI Semibold", 24),
    "title": ("Segoe UI Semibold", 16),
    "heading": ("Segoe UI Semibold", 13),
    "body": ("Segoe UI", 13),
    "small": ("Segoe UI", 11),
    "mono": ("Cascadia Mono", 12),
}


def _lerp_color(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))

    def hex_rgb(c: str) -> tuple[int, int, int]:
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    ar, ag, ab = hex_rgb(a)
    br, bg, bb = hex_rgb(b)
    r = int(ar + (br - ar) * t)
    g = int(ag + (bg - ag) * t)
    bl = int(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


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
        self._labels: dict[str, Any] = {}
        self._closing = False
        self._pulse_t = 0.0
        self._enter_t = 0.0
        self._toast_job: Optional[str] = None
        self._last_details = ""
        self._rpc_ok = False
        self._anim_cards: list[ctk.CTkFrame] = []

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(APP_NAME)
        self.geometry("540x640")
        self.minsize(500, 600)
        self.configure(fg_color=COLORS["bg"])

        self._build()
        self._load()
        self._apply_lang()
        self.after(16, self._animate_enter)
        self.after(120, self._pulse_loop)
        self.after(350, self._tick)
        if start_minimized:
            self.withdraw()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _lang_code(self) -> str:
        return normalize_lang(str(self.cfg.get("language") or "en"))

    def _build(self) -> None:
        # Soft top accent strip
        self.accent_bar = ctk.CTkFrame(self, fg_color=COLORS["accent"], height=3, corner_radius=0)
        self.accent_bar.pack(fill="x")

        self.root = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.root.pack(fill="both", expand=True, padx=24, pady=20)

        # Header
        top = ctk.CTkFrame(self.root, fg_color="transparent")
        top.pack(fill="x")

        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left", fill="x", expand=True)

        title_row = ctk.CTkFrame(brand, fg_color="transparent")
        title_row.pack(fill="x")
        self.brand_dot = ctk.CTkLabel(
            title_row,
            text="●",
            font=FONTS["title"],
            text_color=COLORS["accent"],
            width=18,
        )
        self.brand_dot.pack(side="left")
        ctk.CTkLabel(
            title_row,
            text=APP_NAME,
            font=FONTS["brand"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        self.subtitle = ctk.CTkLabel(
            brand,
            text="",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.subtitle.pack(fill="x", pady=(2, 0), padx=(18, 0))

        self.status_pill = ctk.CTkLabel(
            top,
            text="○ Offline",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            fg_color=COLORS["surface"],
            corner_radius=999,
            padx=12,
            pady=6,
        )
        self.status_pill.pack(side="right", padx=(12, 0))

        # Controls card
        self.card = ctk.CTkFrame(
            self.root,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.card.pack(fill="x", pady=(18, 0))
        self._anim_cards.append(self.card)

        self.power_btn = ctk.CTkButton(
            self.card,
            text="",
            font=FONTS["title"],
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color="#fff",
            height=46,
            corner_radius=12,
            command=self._toggle,
        )
        self.power_btn.pack(fill="x", padx=18, pady=(18, 12))

        lang_row = ctk.CTkFrame(self.card, fg_color="transparent")
        lang_row.pack(fill="x", padx=18, pady=4)
        self._labels["lang"] = ctk.CTkLabel(
            lang_row, text="", font=FONTS["body"], text_color=COLORS["text"], anchor="w"
        )
        self._labels["lang"].pack(side="left")
        self.lang_menu = ctk.CTkSegmentedButton(
            lang_row,
            values=["EN", "RU"],
            command=self._on_lang,
            font=FONTS["small"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["surface2"],
            unselected_hover_color=COLORS["border"],
            text_color="#071018",
            height=28,
        )
        self.lang_menu.pack(side="right")

        self._switch_keys = (
            ("show_elapsed", "show_elapsed"),
            ("button_enabled", "button_enabled"),
            ("autostart", "autostart"),
        )
        for key, _ in self._switch_keys:
            self._switch(self.card, key)

        self.hint = ctk.CTkLabel(
            self.card,
            text="",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.hint.pack(fill="x", padx=18, pady=(10, 16))

        # Discord-like preview card
        self.prev = ctk.CTkFrame(
            self.root,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.prev.pack(fill="both", expand=True, pady=(14, 0))
        self._anim_cards.append(self.prev)

        prev_head = ctk.CTkFrame(self.prev, fg_color="transparent")
        prev_head.pack(fill="x", padx=18, pady=(16, 10))
        self.preview_title = ctk.CTkLabel(
            prev_head,
            text="",
            font=FONTS["heading"],
            text_color=COLORS["accent"],
            anchor="w",
        )
        self.preview_title.pack(side="left")
        self.kind_badge = ctk.CTkLabel(
            prev_head,
            text="idle",
            font=FONTS["small"],
            text_color=COLORS["accent"],
            fg_color=COLORS["surface2"],
            corner_radius=999,
            padx=10,
            pady=3,
        )
        self.kind_badge.pack(side="right")

        # Fake Discord presence row
        disc = ctk.CTkFrame(
            self.prev,
            fg_color=COLORS["bg2"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        disc.pack(fill="x", padx=18, pady=(0, 12))

        row = ctk.CTkFrame(disc, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=14)

        self.avatar = ctk.CTkFrame(
            row, width=48, height=48, corner_radius=14, fg_color=COLORS["accent_dim"]
        )
        self.avatar.pack(side="left")
        self.avatar.pack_propagate(False)
        ctk.CTkLabel(
            self.avatar, text="C", font=FONTS["title"], text_color="#071018"
        ).place(relx=0.5, rely=0.5, anchor="center")

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, padx=(12, 0))

        ctk.CTkLabel(
            text_col,
            text="Playing Cursor",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x")
        self.preview_details = ctk.CTkLabel(
            text_col,
            text="…",
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        )
        self.preview_details.pack(fill="x", pady=(2, 0))
        self.preview_state = ctk.CTkLabel(
            text_col,
            text="…",
            font=FONTS["body"],
            text_color=COLORS["muted"],
            anchor="w",
            wraplength=340,
            justify="left",
        )
        self.preview_state.pack(fill="x", pady=(2, 0))

        # Live chips
        chips = ctk.CTkFrame(self.prev, fg_color="transparent")
        chips.pack(fill="x", padx=18, pady=(0, 16))
        self.chip_ai = self._chip(chips, "AI")
        self.chip_chat = self._chip(chips, "Chat")
        self.chip_ws = self._chip(chips, "Workspace")

        # Footer
        foot = ctk.CTkFrame(self.root, fg_color="transparent")
        foot.pack(fill="x", pady=(14, 0))
        self.toast = ctk.CTkLabel(
            foot, text="", font=FONTS["small"], text_color=COLORS["accent"], anchor="w"
        )
        self.toast.pack(side="left")
        self.save_btn = ctk.CTkButton(
            foot,
            text="",
            font=FONTS["heading"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#071018",
            height=40,
            width=128,
            corner_radius=12,
            command=self._save,
        )
        self.save_btn.pack(side="right")

        self._sync_power()

    def _chip(self, parent: ctk.CTkFrame, title: str) -> ctk.CTkLabel:
        box = ctk.CTkFrame(
            parent,
            fg_color=COLORS["surface2"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
        )
        box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(
            box, text=title, font=FONTS["small"], text_color=COLORS["muted"], anchor="w"
        ).pack(fill="x", padx=10, pady=(8, 0))
        val = ctk.CTkLabel(
            box, text="—", font=FONTS["heading"], text_color=COLORS["text"], anchor="w"
        )
        val.pack(fill="x", padx=10, pady=(0, 8))
        return val

    def _switch(self, parent, key: str) -> None:
        var = ctk.BooleanVar(value=bool(self.cfg.get(key, False)))
        self._vars[key] = var
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=4)
        label = ctk.CTkLabel(
            row, text="", font=FONTS["body"], text_color=COLORS["text"], anchor="w"
        )
        label.pack(side="left")
        self._labels[key] = label
        ctk.CTkSwitch(
            row,
            text="",
            variable=var,
            progress_color=COLORS["accent"],
            button_color=COLORS["text"],
            button_hover_color=COLORS["accent_hover"],
            command=self._preview,
        ).pack(side="right")

    def _animate_enter(self) -> None:
        if self._closing:
            return
        self._enter_t = min(1.0, self._enter_t + 0.08)
        # Soft border bloom on cards
        border = _lerp_color(COLORS["bg"], COLORS["border"], self._enter_t)
        for card in self._anim_cards:
            try:
                card.configure(border_color=border)
            except Exception:
                pass
        bar = _lerp_color(COLORS["bg"], COLORS["accent"], self._enter_t)
        try:
            self.accent_bar.configure(fg_color=bar)
        except Exception:
            pass
        if self._enter_t < 1.0:
            self.after(16, self._animate_enter)

    def _pulse_loop(self) -> None:
        if self._closing:
            return
        self._pulse_t += 0.12
        wave = (math.sin(self._pulse_t) + 1) * 0.5
        if self._rpc_ok:
            color = _lerp_color(COLORS["accent_dim"], COLORS["accent"], wave)
            try:
                self.brand_dot.configure(text_color=color)
                self.status_pill.configure(
                    text_color=_lerp_color(COLORS["ok"], COLORS["accent"], wave * 0.35)
                )
                self.avatar.configure(
                    fg_color=_lerp_color(COLORS["accent_dim"], COLORS["accent"], wave * 0.5)
                )
            except Exception:
                pass
        else:
            try:
                self.brand_dot.configure(text_color=COLORS["muted"])
            except Exception:
                pass
        self.after(40, self._pulse_loop)

    def _on_lang(self, value: str) -> None:
        self.cfg["language"] = "ru" if value.upper() == "RU" else "en"
        self._apply_lang()
        self._save_quiet()
        self._preview()

    def _apply_lang(self) -> None:
        lang = self._lang_code()
        self.subtitle.configure(text=f"{t(lang, 'subtitle')} · v{APP_VERSION}")
        self._labels["lang"].configure(text=t(lang, "lang"))
        for key, i18n_key in self._switch_keys:
            self._labels[key].configure(text=t(lang, i18n_key))
        self.hint.configure(text=t(lang, "hint"))
        self.preview_title.configure(text=t(lang, "preview"))
        self.save_btn.configure(text=t(lang, "save"))
        self._sync_power()

    def _load(self) -> None:
        for k, var in self._vars.items():
            if k in self.cfg:
                var.set(bool(self.cfg[k]))
        self.lang_menu.set("EN" if self._lang_code() == "en" else "RU")

    def _collect(self) -> dict[str, Any]:
        out = dict(self.cfg)
        for k, var in self._vars.items():
            out[k] = bool(var.get())
        out["language"] = self._lang_code()
        out.setdefault("button_url", REPO_URL)
        out.setdefault("button_label", "GitHub")
        return out

    def _sync_power(self) -> None:
        lang = self._lang_code()
        on = bool(self.cfg.get("enabled", True))
        if on:
            self.power_btn.configure(
                text=t(lang, "disable_rpc"),
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
            )
        else:
            self.power_btn.configure(
                text=t(lang, "enable_rpc"),
                fg_color=COLORS["ok"],
                hover_color=COLORS["ok_hover"],
            )

    def _toggle(self) -> None:
        self.set_enabled_ui(not bool(self.cfg.get("enabled", True)))

    def set_enabled_ui(self, enabled: bool) -> None:
        lang = self._lang_code()
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
        self._flash(t(lang, "rpc_off" if not enabled else "rpc_on"))

    def _save_quiet(self) -> None:
        enabled = bool(self.cfg.get("enabled", True))
        self.cfg = self._collect()
        self.cfg["enabled"] = enabled
        save_config(self.cfg)
        if self.on_save:
            self.on_save(self.cfg)

    def _save(self) -> None:
        self._save_quiet()
        self._flash(t(self._lang_code(), "saved"))
        self._preview()
        # Brief save button flash
        self.save_btn.configure(fg_color=COLORS["ok"])
        self.after(220, lambda: self.save_btn.configure(fg_color=COLORS["accent"]))

    def _flash(self, text: str) -> None:
        if self._toast_job:
            try:
                self.after_cancel(self._toast_job)
            except Exception:
                pass
        self.toast.configure(text=text, text_color=COLORS["accent"])
        self._toast_job = self.after(2200, lambda: self.toast.configure(text=""))

    def _preview(self) -> None:
        lang = self._lang_code()
        cfg = self._collect()
        cfg["enabled"] = bool(self.cfg.get("enabled", True))
        state = CursorState(
            running=True,
            workspace="cursor-discord-rpc",
            chat_name="Discord RPC program",
            activity=t(lang, "act_editing", file="ui.py"),
            kind="editing",
        )
        if self.get_live_state:
            live = self.get_live_state()
            if live.workspace:
                state.workspace = live.workspace
            if live.chat_name:
                state.chat_name = live.chat_name
            if live.activity:
                state.activity = live.activity
            state.kind = live.kind or state.kind

        if not cfg.get("enabled", True):
            self.preview_details.configure(text=t(lang, "rpc_disabled"))
            self.preview_state.configure(text="")
            self.kind_badge.configure(text="off")
            return

        payload = DiscordRPC("0").build_presence(cfg, state)
        details = payload.get("details", "")
        # Flash details when activity changes
        if details != self._last_details:
            self._last_details = details
            self.preview_details.configure(text_color=COLORS["accent"])
            self.after(
                180,
                lambda: self.preview_details.configure(text_color=COLORS["text"]),
            )
            try:
                self.prev.configure(border_color=COLORS["accent"])
                self.after(
                    260,
                    lambda: self.prev.configure(border_color=COLORS["border"]),
                )
            except Exception:
                pass

        self.preview_details.configure(text=details)
        self.preview_state.configure(text=payload.get("state", ""))
        self.kind_badge.configure(text=(state.kind or "idle").upper())

    def _tick(self) -> None:
        if self._closing:
            return
        try:
            self._preview()
            lang = self._lang_code()
            if self.get_live_state:
                s = self.get_live_state()
                self.chip_ai.configure(text=s.activity or "—")
                self.chip_chat.configure(text=s.chat_name or "—")
                self.chip_ws.configure(text=s.workspace or "—")
            if self.get_rpc_status:
                ok, msg = self.get_rpc_status()
                self._rpc_ok = ok
                self.status_pill.configure(
                    text=f"{'●' if ok else '○'} {msg}",
                    text_color=COLORS["ok"] if ok else COLORS["muted"],
                    fg_color=COLORS["surface2"] if ok else COLORS["surface"],
                )
        except Exception:
            pass
        self.after(400, self._tick)

    def _on_close(self) -> None:
        self.withdraw()

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def destroy_app(self) -> None:
        self._closing = True
        self.destroy()
