"""Live Cursor state from transcripts + recently touched workspace files."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

USER_QUERY_RE = re.compile(
    r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL | re.IGNORECASE
)
TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>", re.DOTALL | re.IGNORECASE)
EDIT_TOOLS = {"Write", "StrReplace", "EditNotebook", "Delete"}
READ_TOOLS = {"Read", "Grep", "Glob"}
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
    ".txt",
}
SKIP_DIR_NAMES = {
    ".git",
    "dist",
    "build",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".cursor",
}


@dataclass
class CursorState:
    running: bool = False
    workspace: str = ""
    workspace_path: str = ""
    file_name: str = ""
    chat_name: str = ""
    activity_label: str = "В Cursor"
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


def _decode_file_uri(uri: str) -> str:
    if uri.startswith("file:///"):
        return str(Path(urllib.parse.unquote(uri[len("file:///") :])))
    return uri


def _workspace_info() -> tuple[str, str]:
    """Newest non-empty workspace folder from workspaceStorage."""
    root = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    if not root.exists():
        return "", ""
    best: Optional[tuple[float, str, str]] = None
    try:
        for d in root.iterdir():
            wj = d / "workspace.json"
            if not wj.exists():
                continue
            try:
                data = json.loads(wj.read_text(encoding="utf-8"))
                m = wj.stat().st_mtime
            except (OSError, json.JSONDecodeError):
                continue
            folder = data.get("folder") or ""
            if not (isinstance(folder, str) and folder.startswith("file:///")):
                continue
            full = _decode_file_uri(folder)
            name = Path(full).name
            if not name:
                continue
            # Prefer recently touched state DB inside this workspace
            db = d / "state.vscdb"
            try:
                if db.exists():
                    m = max(m, db.stat().st_mtime)
            except OSError:
                pass
            if best is None or m > best[0]:
                best = (m, name, full)
    except OSError:
        return "", ""
    if not best:
        return "", ""
    return best[1], best[2]


def _project_dir(workspace_path: str) -> Optional[Path]:
    root = Path.home() / ".cursor" / "projects"
    if not root.exists() or not workspace_path:
        return None
    name = Path(workspace_path).name.lower().replace(" ", "-")
    try:
        matches = [
            p
            for p in root.iterdir()
            if p.is_dir() and not p.name.startswith(".") and name in p.name.lower()
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda p: max(
                (
                    f.stat().st_mtime
                    for f in (p / "agent-transcripts").rglob("*.jsonl")
                ),
                default=p.stat().st_mtime,
            ),
        )
    except OSError:
        return None


def _newest_transcript(project: Optional[Path]) -> Optional[Path]:
    roots: list[Path] = []
    if project is not None:
        roots.append(project / "agent-transcripts")
    else:
        base = Path.home() / ".cursor" / "projects"
        if base.exists():
            try:
                roots.extend(p / "agent-transcripts" for p in base.iterdir() if p.is_dir())
            except OSError:
                return None
    newest: Optional[Path] = None
    newest_mtime = 0.0
    for root in roots:
        if not root.exists():
            continue
        try:
            for f in root.rglob("*.jsonl"):
                try:
                    m = f.stat().st_mtime
                except OSError:
                    continue
                if m > newest_mtime:
                    newest_mtime, newest = m, f
        except OSError:
            continue
    return newest


def _clean_chat_title(raw: str) -> str:
    text = TIMESTAMP_RE.sub("", raw)
    m = USER_QUERY_RE.search(text)
    if m:
        text = m.group(1)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    text = text.split(". ")[0].strip()
    words = text.split()
    if len(words) > 8:
        text = " ".join(words[:8])
    if len(text) > 48:
        text = text[:45].rstrip() + "…"
    return text


def _message_parts(obj: dict[str, Any]) -> list[Any]:
    msg = obj.get("message")
    content: Any = None
    if isinstance(msg, dict):
        content = msg.get("content")
    if content is None:
        content = obj.get("content")
    return content if isinstance(content, list) else []


def _parse_transcript(path: Path) -> tuple[str, str, float]:
    """chat, file, transcript_mtime"""
    try:
        transcript_mtime = path.stat().st_mtime
        raw = path.read_bytes()
        if len(raw) > 150_000:
            raw = raw[-150_000:]
            text = raw.decode("utf-8", errors="ignore").split("\n", 1)[-1]
        else:
            text = raw.decode("utf-8", errors="ignore")
        lines = text.splitlines()
    except OSError:
        return "", "", 0.0

    chat_first = ""
    chat_last = ""
    edit_file = ""
    read_file = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        role = str(obj.get("role") or "").lower()
        if role in ("user", "human"):
            parts = []
            for part in _message_parts(obj):
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
            title = _clean_chat_title("\n".join(parts)) if parts else ""
            if title:
                if not chat_first:
                    chat_first = title
                chat_last = title

        for part in _message_parts(obj):
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            name = str(part.get("name") or "")
            inp = part.get("input") or {}
            if not isinstance(inp, dict):
                continue
            raw_path = inp.get("path") or inp.get("target_file") or ""
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            fname = Path(raw_path.replace("\\", "/")).name
            if not fname or "." not in fname:
                continue
            if name in EDIT_TOOLS:
                edit_file = fname
            elif name in READ_TOOLS:
                read_file = fname

    chat = chat_first or chat_last
    return chat, (edit_file or read_file), transcript_mtime


def _recent_workspace_file(workspace_path: str, max_age_sec: float = 900) -> tuple[str, float]:
    """Most recently modified code file in the workspace."""
    if not workspace_path:
        return "", 0.0
    root = Path(workspace_path)
    if not root.is_dir():
        return "", 0.0
    newest_name = ""
    newest_mtime = 0.0
    now = time.time()
    try:
        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if any(part in SKIP_DIR_NAMES for part in p.parts):
                    continue
                if p.suffix.lower() not in CODE_EXTS:
                    continue
                m = p.stat().st_mtime
                if now - m > max_age_sec:
                    continue
                if m > newest_mtime:
                    newest_mtime, newest_name = m, p.name
            except OSError:
                continue
    except OSError:
        return "", 0.0
    return newest_name, newest_mtime


def _pick_file(
    tool_file: str,
    transcript_mtime: float,
    disk_file: str,
    disk_mtime: float,
) -> str:
    """Disk wins if the file was touched after the transcript; else AI tool path."""
    if disk_file and disk_mtime > (transcript_mtime or 0):
        return disk_file
    if tool_file:
        return tool_file
    return disk_file


class CursorWatcher:
    def __init__(self) -> None:
        self._state = CursorState()
        self._last_file = ""
        self._last_chat = ""

    @property
    def state(self) -> CursorState:
        return self._state

    def refresh(self) -> CursorState:
        running = is_cursor_running()
        ws_name, ws_path = _workspace_info()
        chat, file_name, activity = "", "", "В Cursor"

        if running:
            project = _project_dir(ws_path)
            transcript = _newest_transcript(project) or _newest_transcript(None)
            tool_file, t_mtime = "", 0.0
            if transcript is not None:
                chat, tool_file, t_mtime = _parse_transcript(transcript)

            disk_file, disk_mtime = _recent_workspace_file(ws_path)
            file_name = _pick_file(tool_file, t_mtime, disk_file, disk_mtime)

            age = time.time() - t_mtime if t_mtime else 9999
            disk_age = time.time() - disk_mtime if disk_mtime else 9999
            if age < 90 or disk_age < 90:
                if file_name:
                    activity = "Редактирует файл"
                elif chat:
                    activity = "Чат с AI"
                else:
                    activity = "В Cursor"
            elif file_name:
                activity = "Редактирует файл"
            elif chat:
                activity = "Чат с AI"

            # Sticky: don't blank out file/chat on brief misses
            if file_name:
                self._last_file = file_name
            elif self._last_file:
                file_name = self._last_file
            if chat:
                self._last_chat = chat
            elif self._last_chat:
                chat = self._last_chat

        self._state = CursorState(
            running=running,
            workspace=ws_name,
            workspace_path=ws_path,
            file_name=file_name,
            chat_name=chat,
            activity_label=activity,
            updated_at=time.time(),
        )
        return self._state
