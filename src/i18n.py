"""EN / RU strings for UI and Discord presence."""

from __future__ import annotations

from typing import Any

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "subtitle": "Rich Presence for Cursor",
        "offline": "Offline",
        "disable_rpc": "Disable RPC",
        "enable_rpc": "Enable RPC",
        "show_elapsed": "Session timer",
        "button_enabled": "GitHub button (friends see it)",
        "autostart": "Start with Windows",
        "hint": "details — AI activity · state — chat · workspace",
        "preview": "Discord preview",
        "save": "Save",
        "saved": "Saved",
        "rpc_on": "RPC enabled",
        "rpc_off": "RPC disabled",
        "rpc_disabled": "RPC disabled",
        "lang": "Language",
        "cursor_online": "Cursor online",
        "cursor_offline": "Cursor offline",
        "label_ai": "AI",
        "label_chat": "Chat",
        "label_ws": "Workspace",
        "status_connected": "Connected",
        "status_discord_offline": "Discord offline",
        "status_waiting": "Waiting for Cursor",
        "status_disabled": "Disabled",
        "status_error": "Error",
        "status_starting": "Starting",
        "tray_open": "Open",
        "tray_off": "Disable RPC",
        "tray_on": "Enable RPC",
        "tray_quit": "Quit",
        "act_idle": "Idle",
        "act_typing": "Writing a prompt",
        "act_editing": "Editing {file}",
        "act_reading": "Reading {file}",
        "act_shell": "Running commands",
        "act_search": "Searching",
        "act_thinking": "Thinking…",
        "act_chatting": "Replying in chat",
        "act_in_cursor": "In Cursor",
        "chat_fallback": "Active chat",
        "state_fallback": "Cursor IDE",
    },
    "ru": {
        "subtitle": "Rich Presence для Cursor",
        "offline": "Офлайн",
        "disable_rpc": "Отключить RPC",
        "enable_rpc": "Включить RPC",
        "show_elapsed": "Таймер сессии",
        "button_enabled": "Кнопка GitHub (видят друзья)",
        "autostart": "Автозапуск с Windows",
        "hint": "details — что делает AI · state — чат · workspace",
        "preview": "Превью Discord",
        "save": "Сохранить",
        "saved": "Сохранено",
        "rpc_on": "RPC включён",
        "rpc_off": "RPC выключен",
        "rpc_disabled": "RPC выключен",
        "lang": "Язык",
        "cursor_online": "Cursor онлайн",
        "cursor_offline": "Cursor офлайн",
        "label_ai": "AI",
        "label_chat": "Чат",
        "label_ws": "Workspace",
        "status_connected": "Подключено",
        "status_discord_offline": "Discord офлайн",
        "status_waiting": "Ждём Cursor",
        "status_disabled": "Выключено",
        "status_error": "Ошибка",
        "status_starting": "Запуск",
        "tray_open": "Открыть",
        "tray_off": "Отключить RPC",
        "tray_on": "Включить RPC",
        "tray_quit": "Выход",
        "act_idle": "Простой",
        "act_typing": "Пишет промпт",
        "act_editing": "Редактирует {file}",
        "act_reading": "Читает {file}",
        "act_shell": "Выполняет команды",
        "act_search": "Ищет информацию",
        "act_thinking": "Думает…",
        "act_chatting": "Отвечает в чате",
        "act_in_cursor": "В Cursor",
        "chat_fallback": "Активный чат",
        "state_fallback": "Cursor IDE",
    },
}


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "en").strip().lower()
    return lang if lang in STRINGS else "en"


def t(lang: str, key: str, **kwargs: Any) -> str:
    lang = normalize_lang(lang)
    text = STRINGS.get(lang, STRINGS["en"]).get(key) or STRINGS["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
