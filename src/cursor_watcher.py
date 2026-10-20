"""Detect Cursor IDE state: process, workspace, open file, chat, activity."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

SKIP_TITLES = {
    "cursor",
    "cursor agents",
    "cursor settings",
    "cursor: extensions",
}

USER_QUERY_RE = re.compile(
    r"<user_query>\s*(.*?)\s*</user_query>",
    re.DOTALL | re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>", re.DOTALL | re.IGNORECASE)
FILE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|]+?\.\w{1,8})|(?:(?:src|scripts|assets)/[^\s\"'<>|]+?\.\w{1,8})",
    re.IGNORECASE,
)
CODE_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".ps1",
    ".css",
    ".html",
    ".cs",
    ".go",
    ".rs",
    ".java",
    ".cpp",
    ".h",
    ".yml",
    ".yaml",
    ".toml",
}


@dataclass
class CursorState:
    running: bool = False
    window_title: str = ""
    workspace: str = ""
    workspace_path: str = ""
    file_name: str = ""
    chat_name: str = ""
    activity_hint: str = "editing"
    activity_label: str = "Редактирует файл"
    updated_at: float = field(default_factory=time.time)


def is_cursor_running() -> bool:
    if psutil is None:
        return True
    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() == "cursor.exe":
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
                if psutil.Process(pid.value).name().lower() == "cursor.exe":
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

    return sorted(titles, key=score)[0] if titles else ""


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


def _decode_file_uri(uri: str) -> str:
    if uri.startswith("file:///"):
        raw = urllib.parse.unquote(uri[len("file:///") :])
        return str(Path(raw))
    return uri


def _workspace_info() -> tuple[str, str]:
    """Return (folder_name, full_path) from newest workspaceStorage entry."""
    root = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    if not root.exists():
        return "", ""
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
        return "", ""
    if not newest:
        return "", ""
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    folder = data.get("folder") or ""
    if isinstance(folder, str) and folder.startswith("file:///"):
        full = _decode_file_uri(folder)
        return Path(full).name, full
    return "", ""


def _project_dir_for_workspace(workspace_path: str) -> Optional[Path]:
    root = Path.home() / ".cursor" / "projects"
    if not root.exists() or not workspace_path:
        return None
    # Cursor encodes paths like c-Users-admin-Documents-cursor-discord-rpc
    norm = re.sub(r"[^A-Za-z0-9]+", "-", workspace_path).strip("-")
    candidates = [
        root / norm,
        root / norm.replace("C-", "c-"),
        root / workspace_path.replace("\\", "-").replace(":", "").replace(" ", "-"),
    ]
    # Also fuzzy: folder name in project id
    name = Path(workspace_path).name
    try:
        for p in root.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            if name.lower().replace(" ", "-") in p.name.lower():
                candidates.append(p)
    except OSError:
        pass
    for c in candidates:
        if c.exists():
            return c
    return None


def _extract_text_from_message(obj: dict[str, Any]) -> str:
    msg = obj.get("message")
    content: Any = None
    if isinstance(msg, dict):
        content = msg.get("content")
    if content is None:
        content = obj.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    if isinstance(obj.get("text"), str):
        return obj["text"]
    return ""


def _clean_chat_title(raw: str) -> str:
    text = TIMESTAMP_RE.sub("", raw)
    m = USER_QUERY_RE.search(text)
    if m:
        text = m.group(1)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    # First sentence, then first few words — Discord line is tiny
    text = text.split(". ")[0].strip()
    words = text.split()
    if len(words) > 6:
        text = " ".join(words[:6])
    if len(text) > 36:
        text = text[:33].rstrip() + "…"
    return text


def _iter_transcripts(project: Optional[Path] = None) -> list[Path]:
    roots: list[Path] = []
    if project is not None:
        roots.append(project / "agent-transcripts")
    else:
        base = Path.home() / ".cursor" / "projects"
        if base.exists():
            try:
                roots.extend(p / "agent-transcripts" for p in base.iterdir() if p.is_dir())
            except OSError:
                pass
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            files.extend(root.rglob("*.jsonl"))
        except OSError:
            continue
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return files


def _latest_chat_and_file(
    workspace_path: str = "",
) -> tuple[str, str, float]:
    """Return (chat_title, file_name, transcript_mtime)."""
    project = _project_dir_for_workspace(workspace_path) if workspace_path else None
    files = _iter_transcripts(project)
    if not files and project is not None:
        files = _iter_transcripts(None)
    if not files:
        return "", "", 0.0

    newest = files[0]
    try:
        mtime = newest.stat().st_mtime
    except OSError:
        mtime = 0.0

    chat = ""
    file_name = ""
    try:
        lines = newest.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return newest.stem[:8], "", mtime

    # Chat title from first user message
    for line in lines[:80]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = str(obj.get("role") or "").lower()
        if role not in ("user", "human"):
            continue
        title = _clean_chat_title(_extract_text_from_message(obj))
        if title:
            chat = title
            break

    # Most recently mentioned code file in the transcript tail
    for line in reversed(lines[-120:]):
        for m in FILE_PATH_RE.finditer(line):
            raw = m.group(0).strip("\"'` ")
            path = Path(raw.replace("\\", "/"))
            if path.suffix.lower() in CODE_EXTS:
                file_name = path.name
                break
        if file_name:
            break

    if not chat:
        chat = newest.stem[:8]
    return chat, file_name, mtime


def _file_from_history() -> str:
    root = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    if not root.exists():
        return ""
    newest_path = ""
    newest_mtime = 0.0
    try:
        for d in root.iterdir():
            db = d / "state.vscdb"
            if not db.exists():
                continue
            try:
                m = db.stat().st_mtime
            except OSError:
                continue
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                row = con.execute(
                    "SELECT value FROM ItemTable WHERE key=?",
                    ("history.entries",),
                ).fetchone()
                con.close()
            except sqlite3.Error:
                continue
            if not row:
                continue
            try:
                entries = json.loads(row[0])
            except json.JSONDecodeError:
                continue
            if not entries:
                continue
            resource = (
                entries[0].get("editor", {}).get("resource")
                if isinstance(entries[0], dict)
                else None
            )
            if isinstance(resource, str) and resource.startswith("file:"):
                name = Path(_decode_file_uri(resource)).name
                if m >= newest_mtime and name:
                    newest_mtime = m
                    newest_path = name
    except OSError:
        return newest_path
    return newest_path


def _guess_activity(
    file_name: str, chat_name: str, title: str, transcript_mtime: float
) -> tuple[str, str]:
    recent_ai = transcript_mtime and (time.time() - transcript_mtime) < 180
    lower = f"{file_name} {title} {chat_name}".lower()
    if recent_ai:
        if file_name:
            return "editing", "Редактирует файл"
        return "chatting", "Чат с AI"
    if any(x in lower for x in ("debug", "отлад")):
        return "debugging", "Отладка"
    if any(x in lower for x in ("test_", "_test", ".spec.")):
        return "testing", "Пишет тесты"
    if file_name.endswith(".md") or "readme" in lower:
        return "docs", "Пишет документацию"
    if file_name:
        return "editing", "Редактирует файл"
    if chat_name:
        return "chatting", "Чат с AI"
    return "writing", "Пишет код"


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
        ws_name, ws_path = _workspace_info()
        if not workspace:
            workspace = ws_name

        chat, transcript_file, transcript_mtime = ("", "", 0.0)
        if running:
            chat, transcript_file, transcript_mtime = _latest_chat_and_file(ws_path)
        if not file_name:
            file_name = transcript_file or _file_from_history()

        hint, label = _guess_activity(file_name, chat, title, transcript_mtime)

        self._state = CursorState(
            running=running,
            window_title=title,
            workspace=workspace,
            workspace_path=ws_path,
            file_name=file_name,
            chat_name=chat if running else "",
            activity_hint=hint,
            activity_label=label,
            updated_at=time.time(),
        )
        return self._state
