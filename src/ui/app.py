"""Settings window for Cursor Discord RPC."""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Callable, Optional

import customtkinter as ctk

from ..config import ACTIVITY_PRESETS, APP_NAME, APP_VERSION, REPO_URL, save_config
from ..cursor_watcher import CursorState
from .styles import COLORS, FONTS


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

        self.title(f"{APP_NAME}")
        self.geometry("920x680")
        self.minsize(820, 600)
        self.configure(fg_color=COLORS["bg"])

        self._build()
        self._load_into_ui()
        self.after(800, self._tick_preview)

        if start_minimized:
            self.withdraw()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── layout ──────────────────────────────────────────────
    def _build(self) -> None:
        root = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        root.pack(fill="both", expand=True, padx=18, pady=18)
        root.grid_columnconfigure(0, weight=3)
        root.grid_columnconfigure(1, weight=2)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")

        self.status_pill = ctk.CTkLabel(
            header,
            text="● Offline",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            fg_color=COLORS["surface"],
            corner_radius=999,
            padx=12,
            pady=6,
        )
        self.status_pill.grid(row=0, column=1, sticky="e")

        subtitle = ctk.CTkLabel(
            header,
            text="Настрой что видно в Discord · v" + APP_VERSION,
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        left = ctk.CTkScrollableFrame(
            root,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        right = ctk.CTkFrame(
            root,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        right.grid(row=1, column=1, sticky="nsew")

        self._section_presence(left)
        self._section_activity(left)
        self._section_button(left)
        self._section_system(left)
        self._section_preview(right)

        footer = ctk.CTkFrame(root, fg_color="transparent")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.grid_columnconfigure(0, weight=1)

        self.toast = ctk.CTkLabel(
            footer,
            text="",
            font=FONTS["small"],
            text_color=COLORS["accent"],
            anchor="w",
        )
        self.toast.grid(row=0, column=0, sticky="w")

        save_btn = ctk.CTkButton(
            footer,
            text="Сохранить",
            font=FONTS["heading"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#071018",
            corner_radius=10,
            height=40,
            width=140,
            command=self._save,
        )
        save_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        apply_btn = ctk.CTkButton(
            footer,
            text="Применить",
            font=FONTS["heading"],
            fg_color=COLORS["surface2"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10,
            height=40,
            width=120,
            command=self._apply,
        )
        apply_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _heading(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=FONTS["heading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 8))

    def _switch(self, parent, key: str, label: str) -> None:
        var = ctk.BooleanVar(value=bool(self.cfg.get(key, False)))
        self._vars[key] = var
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(
            row, text=label, font=FONTS["body"], text_color=COLORS["text"], anchor="w"
        ).pack(side="left")
        ctk.CTkSwitch(
            row,
            text="",
            variable=var,
            progress_color=COLORS["accent"],
            button_color=COLORS["text"],
            button_hover_color=COLORS["accent_hover"],
            command=self._refresh_preview,
        ).pack(side="right")

    def _entry(self, parent, key: str, label: str, placeholder: str = "") -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(8, 2))
        var = ctk.StringVar(value=str(self.cfg.get(key, "")))
        self._vars[key] = var
        entry = ctk.CTkEntry(
            parent,
            textvariable=var,
            placeholder_text=placeholder,
            font=FONTS["body"],
            fg_color=COLORS["surface2"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=36,
            corner_radius=8,
        )
        entry.pack(fill="x", padx=16, pady=(0, 4))
        var.trace_add("write", lambda *_: self._refresh_preview())

    def _section_presence(self, parent) -> None:
        self._heading(parent, "Что показывать")
        self._switch(parent, "enabled", "Включить Rich Presence")
        self._switch(parent, "show_activity", "Активность AI / статус")
        self._switch(parent, "show_file", "Имя файла")
        self._switch(parent, "show_workspace", "Название проекта")
        self._switch(parent, "show_chat", "Название чата")
        self._switch(parent, "show_elapsed", "Время сессии")

    def _section_activity(self, parent) -> None:
        self._heading(parent, "Активность")
        ctk.CTkLabel(
            parent,
            text="Режим",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(4, 2))

        labels = list(ACTIVITY_PRESETS.values())
        keys = list(ACTIVITY_PRESETS.keys())
        self._activity_keys = keys
        current = self.cfg.get("activity_mode", "auto")
        display = ACTIVITY_PRESETS.get(current, ACTIVITY_PRESETS["auto"])
        var = ctk.StringVar(value=display)
        self._vars["activity_mode_display"] = var
        self._vars["activity_mode"] = current

        menu = ctk.CTkOptionMenu(
            parent,
            values=labels,
            variable=var,
            font=FONTS["body"],
            fg_color=COLORS["surface2"],
            button_color=COLORS["accent_dim"],
            button_hover_color=COLORS["accent"],
            dropdown_fg_color=COLORS["surface2"],
            dropdown_hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=8,
            height=36,
            command=self._on_activity_change,
        )
        menu.pack(fill="x", padx=16, pady=(0, 4))

        self._entry(parent, "custom_activity", "Свой текст активности", "Пишет код…")
        self._entry(parent, "manual_chat_name", "Чат вручную (пусто = авто)", "Refactor auth")
        self._entry(parent, "custom_details", "Свой details (пусто = авто)", "")
        self._entry(parent, "custom_state", "Свой state (пусто = авто)", "")

    def _section_button(self, parent) -> None:
        self._heading(parent, "Кнопка в Discord")
        self._switch(parent, "button_enabled", "Показывать кнопку")
        self._entry(parent, "button_label", "Текст кнопки", "GitHub")
        self._entry(parent, "button_url", "Ссылка", REPO_URL)

    def _section_system(self, parent) -> None:
        self._heading(parent, "Система")
        self._switch(parent, "autostart", "Автозапуск с Windows / Cursor")
        self._switch(parent, "only_when_cursor_running", "Только когда Cursor запущен")
        self._switch(parent, "start_minimized", "Сворачивать в трей при старте")
        self._entry(
            parent,
            "discord_client_id",
            "Discord Application Client ID",
            "создай на discord.com/developers",
        )
        tip = ctk.CTkLabel(
            parent,
            text="Создай Application → Rich Presence → Art Assets (ключ: cursor)",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
            wraplength=420,
        )
        tip.pack(fill="x", padx=16, pady=(2, 16))

    def _section_preview(self, parent) -> None:
        pad = ctk.CTkFrame(parent, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            pad,
            text="Превью Discord",
            font=FONTS["heading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        card = ctk.CTkFrame(
            pad,
            fg_color=COLORS["preview_bg"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=14)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        avatar = ctk.CTkFrame(
            top, width=56, height=56, corner_radius=12, fg_color=COLORS["accent_dim"]
        )
        avatar.pack(side="left")
        avatar.pack_propagate(False)
        ctk.CTkLabel(
            avatar, text="⌘", font=("Segoe UI Semibold", 22), text_color="#071018"
        ).place(relx=0.5, rely=0.5, anchor="center")

        meta = ctk.CTkFrame(top, fg_color="transparent")
        meta.pack(side="left", fill="x", expand=True, padx=(12, 0))

        ctk.CTkLabel(
            meta,
            text="Играет в Cursor",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x")

        self.preview_details = ctk.CTkLabel(
            meta,
            text="Редактирует файл",
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        )
        self.preview_details.pack(fill="x")

        self.preview_state = ctk.CTkLabel(
            meta,
            text="main.py · cursor-discord-rpc",
            font=FONTS["body"],
            text_color=COLORS["muted"],
            anchor="w",
            wraplength=240,
            justify="left",
        )
        self.preview_state.pack(fill="x", pady=(2, 0))

        self.preview_time = ctk.CTkLabel(
            meta,
            text="00:12 elapsed",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.preview_time.pack(fill="x", pady=(4, 0))

        self.preview_btn = ctk.CTkButton(
            card,
            text="GitHub",
            font=FONTS["small"],
            fg_color=COLORS["surface2"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            height=32,
            corner_radius=8,
            state="disabled",
        )
        self.preview_btn.pack(fill="x", padx=14, pady=(0, 14))

        live = ctk.CTkFrame(pad, fg_color="transparent")
        live.pack(fill="x", pady=(18, 0))
        ctk.CTkLabel(
            live,
            text="Живой статус Cursor",
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x")
        self.live_label = ctk.CTkLabel(
            live,
            text="Ожидание…",
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self.live_label.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(
            pad,
            text=REPO_URL.replace("https://", ""),
            font=FONTS["small"],
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(side="bottom", fill="x", pady=(20, 0))

    # ── data binding ────────────────────────────────────────
    def _on_activity_change(self, display: str) -> None:
        for k, v in ACTIVITY_PRESETS.items():
            if v == display:
                self._vars["activity_mode"] = k
                break
        self._refresh_preview()

    def _collect(self) -> dict[str, Any]:
        out = dict(self.cfg)
        for key, var in self._vars.items():
            if key == "activity_mode_display":
                continue
            if key == "activity_mode":
                out["activity_mode"] = self._vars.get("activity_mode", "auto")
                continue
            if isinstance(var, (ctk.BooleanVar, tk.BooleanVar)):
                out[key] = bool(var.get())
            elif isinstance(var, (ctk.StringVar, tk.StringVar)):
                out[key] = var.get().strip()
        # activity from display
        display = self._vars.get("activity_mode_display")
        if display is not None:
            d = display.get()
            for k, v in ACTIVITY_PRESETS.items():
                if v == d:
                    out["activity_mode"] = k
                    break
        return out

    def _load_into_ui(self) -> None:
        for key, var in self._vars.items():
            if key in ("activity_mode", "activity_mode_display"):
                continue
            if key in self.cfg and hasattr(var, "set"):
                var.set(self.cfg[key])
        mode = self.cfg.get("activity_mode", "auto")
        self._vars["activity_mode"] = mode
        if "activity_mode_display" in self._vars:
            self._vars["activity_mode_display"].set(
                ACTIVITY_PRESETS.get(mode, ACTIVITY_PRESETS["auto"])
            )

    def _apply(self) -> None:
        self.cfg = self._collect()
        if self.on_save:
            self.on_save(self.cfg)
        self._flash("Применено")
        self._refresh_preview()

    def _save(self) -> None:
        self.cfg = self._collect()
        save_config(self.cfg)
        if self.on_save:
            self.on_save(self.cfg)
        self._flash("Сохранено")

    def _flash(self, text: str) -> None:
        self.toast.configure(text=text)
        self.after(2200, lambda: self.toast.configure(text=""))

    def _refresh_preview(self) -> None:
        cfg = self._collect()
        state = CursorState(
            running=True,
            workspace="cursor-discord-rpc",
            file_name="main.py",
            chat_name=cfg.get("manual_chat_name") or "Настройка RPC",
            activity_label="Редактирует файл",
        )
        if self.get_live_state:
            live = self.get_live_state()
            if live.workspace:
                state.workspace = live.workspace
            if live.file_name:
                state.file_name = live.file_name
            if live.chat_name and not cfg.get("manual_chat_name"):
                state.chat_name = live.chat_name
            if live.activity_label:
                state.activity_label = live.activity_label

        from ..rpc_client import DiscordRPC

        payload = DiscordRPC("0").build_presence(cfg, state)
        self.preview_details.configure(text=payload.get("details", ""))
        self.preview_state.configure(text=payload.get("state", ""))
        if cfg.get("show_elapsed", True):
            self.preview_time.configure(text="elapsed time")
        else:
            self.preview_time.configure(text="")

        if cfg.get("button_enabled", True):
            self.preview_btn.configure(text=cfg.get("button_label") or "GitHub")
            self.preview_btn.pack(fill="x", padx=14, pady=(0, 14))
        else:
            self.preview_btn.pack_forget()

        if not cfg.get("enabled", True):
            self.preview_details.configure(text="RPC выключен")
            self.preview_state.configure(text="")

    def _tick_preview(self) -> None:
        if self._closing:
            return
        try:
            self._refresh_preview()
            if self.get_live_state:
                s = self.get_live_state()
                self.live_label.configure(
                    text=(
                        f"{'● Cursor online' if s.running else '○ Cursor offline'}\n"
                        f"Файл: {s.file_name or '—'}\n"
                        f"Проект: {s.workspace or '—'}\n"
                        f"Чат: {s.chat_name or '—'}\n"
                        f"Активность: {s.activity_label}"
                    )
                )
            if self.get_rpc_status:
                ok, msg = self.get_rpc_status()
                self.status_pill.configure(
                    text=f"● {msg}" if ok else f"○ {msg}",
                    text_color=COLORS["ok"] if ok else COLORS["muted"],
                )
        except Exception:
            pass
        self.after(1500, self._tick_preview)

    def _on_close(self) -> None:
        # Hide to tray instead of quit — tray owns lifecycle
        self.withdraw()

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def destroy_app(self) -> None:
        self._closing = True
        self.destroy()
