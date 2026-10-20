"""Detect Cursor IDE state: process, window title, workspace, chat hints."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

CURSOR_PROCESS_NAMES = {
    "cursor.exe",
    "cursor",
    "cursor helper.exe",
    "cursor helper (renderer).exe",
}

SKIP_TITLES = {
    "cursor",
    "cursor agents",
    "cursor settings",
    "cursor: extensions",
}


@dataclass
class CursorState:
    running: bool = False
    window_title: str = ""
    workspace: str = ""
    file_name: str = ""
    chat_name: str = ""
    activity_hint: str = "editing"
    activity_label: str = "Редактирует файл"
    updated_at: float = field(default_factory=time.time)


def _is_cursor_proc(name: str) -> bool:
    n = name.lower()
    return n in CURSOR_PROCESS_NAMES or n.startswith("cursor")


def is_cursor_running() -> bool:
    if psutil is None:
        return True
    try:
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name == "cursor.exe":
                return True
    except (psutil.Error, OSError):
        pass
    return False


def _get_cursor_window_titles() -> list[str]:
    if psutil is None:
        return []
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        titles: list[str] = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc = psutil.Process(pid.value)
                if proc.name().lower() == "cursor.exe":
                    titles.append(title)
            except (psutil.Error, OSError, ValueError):
                pass
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return titles
    except Exception:
        return []


def _pick_best_title(titles: list[str]) -> str:
    def score(t: str) -> tuple:
        low = t.lower().strip()
        if low in SKIP_TITLES:
            return (9, 0)
        has_sep = any(s in t for s in (" — ", " – ", " - "))
        looks_file = bool(re.search(r"\.\w{1,8}\b", t))
        return (0 if has_sep else 1, 0 if looks_file else 1, -len(t))

    if not titles:
        return ""
    return sorted(titles, key=score)[0]


def _parse_title(title: str) -> tuple[str, str]:
    if not title:
        return "", ""
    cleaned = re.sub(r"\s*[-—–]\s*Cursor\s*$", "", title, flags=re.I).strip()
    cleaned = re.sub(
        r"\s*[-—–]\s*Visual Studio Code\s*$", "", cleaned, flags=re.I
    ).strip()
    if cleaned.lower() in SKIP_TITLES:
        return "", ""

    for sep in (" — ", " – ", " - "):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            left, right = left.strip(), right.strip()
            if re.search(r"\.\w{1,8}$", left) or "/" in left or "\\" in left:
                return Path(left).name, right
            return "", cleaned
    if re.search(r"\.\w{1,8}$", cleaned):
        return Path(cleaned).name, ""
    return "", cleaned


def _guess_activity(file_name: str, chat_name: str, title: str) -> tuple[str, str]:
    lower = f"{file_name} {title} {chat_name}".lower()
    if chat_name and not file_name:
        return "chatting", "Чат с AI"
    if any(x in lower for x in ("debug", "отлад")):
        return "debugging", "Отладка"
    if any(x in lower for x in ("test_", "_test", ".spec.", "тест")):
        return "testing", "Пишет тесты"
    if any(x in lower for x in ("readme", ".md")):
        return "docs", "Пишет документацию"
    if any(x in lower for x in ("refactor", "рефактор")):
        return "refactoring", "Рефакторинг"
    if file_name:
        return "editing", "Редактирует файл"
    return "writing", "Пишет код"


def _workspace_from_storage() -> str:
    root = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    if not root.exists():
        return ""
    newest: Optional[Path] = None
    newest_mtime = 0.0
    try:
        for d in root.iterdir():
            wj = d / "workspace.json"
            if not wj.exists():
                continue
            try:
                m = wj.stat().st_mtime
            except OSError:
                continue
            if m > newest_mtime:
                newest_mtime = m
                newest = wj
    except OSError:
        return ""
    if not newest:
        return ""
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    folder = data.get("folder") or ""
    if isinstance(folder, str) and folder.startswith("file:///"):
        raw = folder[len("file:///") :]
        raw = urllib.parse.unquote(raw)
        return Path(raw).name
    return ""


def _latest_chat_name() -> str:
    root = Path.home() / ".cursor" / "projects"
    if not root.exists():
        return ""
    newest: Optional[Path] = None
    newest_mtime = 0.0
    try:
        for project in root.iterdir():
            transcripts = project / "agent-transcripts"
            if not transcripts.is_dir():
                continue
            for f in transcripts.glob("*.jsonl"):
                try:
                    m = f.stat().st_mtime
                except OSError:
                    continue
                if m > newest_mtime:
                    newest_mtime = m
                    newest = f
    except OSError:
        return ""

    if not newest:
        return ""

    # Prefer a companion title file if Cursor wrote one
    for sibling in (newest.with_suffix(".txt"), newest.parent / "title.txt"):
        try:
            if sibling.exists():
                t = sibling.read_text(encoding="utf-8", errors="ignore").strip()
                if t:
                    return t[:48] + ("…" if len(t) > 48 else "")
        except OSError:
            pass

    try:
        with newest.open(encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh):
                if i > 60:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = str(obj.get("role") or obj.get("type") or "").lower()
                text = ""
                content = obj.get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = str(part.get("text") or "")
                            break
                elif isinstance(obj.get("message"), str):
                    text = obj["message"]
                elif isinstance(obj.get("text"), str):
                    text = obj["text"]
                if role in ("user", "human") and text.strip():
                    title = text.strip().splitlines()[0]
                    title = re.sub(r"\s+", " ", title)
                    return title[:48] + ("…" if len(title) > 48 else "")
    except OSError:
        pass
    return newest.stem[:8]


def _activity_from_recent_transcript(chat_name: str) -> Optional[tuple[str, str]]:
    """If an agent transcript was updated in the last ~2 minutes, show AI activity."""
    root = Path.home() / ".cursor" / "projects"
    if not root.exists():
        return None
    newest_mtime = 0.0
    try:
        for project in root.iterdir():
            transcripts = project / "agent-transcripts"
            if not transcripts.is_dir():
                continue
            for f in transcripts.glob("*.jsonl"):
                try:
                    m = f.stat().st_mtime
                except OSError:
                    continue
                if m > newest_mtime:
                    newest_mtime = m
    except OSError:
        return None
    if newest_mtime and (time.time() - newest_mtime) < 120:
        if chat_name:
            return "chatting", "Чат с AI"
        return "writing", "Пишет код"
    return None


class CursorWatcher:
    def __init__(self) -> None:
        self._state = CursorState()

    @property
    def state(self) -> CursorState:
        return self._state

    def refresh(self) -> CursorState:
        running = is_cursor_running()
        title = _pick_best_title(_get_cursor_window_titles()) if running else ""
        file_name, workspace = _parse_title(title)
        if not workspace:
            workspace = _workspace_from_storage()
        chat = _latest_chat_name() if running else ""
        ai = _activity_from_recent_transcript(chat) if running else None
        if ai:
            hint, label = ai
        else:
            hint, label = _guess_activity(file_name, chat, title)

        self._state = CursorState(
            running=running,
            window_title=title,
            workspace=workspace,
            file_name=file_name,
            chat_name=chat,
            activity_hint=hint,
            activity_label=label,
            updated_at=time.time(),
        )
        return self._state
