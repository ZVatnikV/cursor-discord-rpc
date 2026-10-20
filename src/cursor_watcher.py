"""Live Cursor state: workspace, chat title, current file from agent tools."""

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
                newest_mtime, newest = m, wj
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


def _project_dir(workspace_path: str) -> Optional[Path]:
    root = Path.home() / ".cursor" / "projects"
    if not root.exists() or not workspace_path:
        return None
    name = Path(workspace_path).name.lower().replace(" ", "-")
    try:
        # Prefer exact-ish match for this workspace
        matches = [
            p
            for p in root.iterdir()
            if p.is_dir() and not p.name.startswith(".") and name in p.name.lower()
        ]
        if matches:
            return max(
                matches,
                key=lambda p: (p / "agent-transcripts").stat().st_mtime
                if (p / "agent-transcripts").exists()
                else p.stat().st_mtime,
            )
    except OSError:
        pass
    return None


def _newest_transcript(project: Optional[Path]) -> Optional[Path]:
    roots: list[Path] = []
    if project is not None:
        roots.append(project / "agent-transcripts")
    else:
        base = Path.home() / ".cursor" / "projects"
        if base.exists():
            try:
                roots.extend(
                    p / "agent-transcripts" for p in base.iterdir() if p.is_dir()
                )
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
    if isinstance(content, list):
        return content
    return []


def _parse_transcript(path: Path) -> tuple[str, str, str, float]:
    """Return chat_title, file_name, activity_label, mtime."""
    try:
        mtime = path.stat().st_mtime
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return "", "", "В Cursor", 0.0

    chat = ""
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
        if role in ("user", "human") and not chat:
            text_parts = []
            for part in _message_parts(obj):
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text") or ""))
            if text_parts:
                chat = _clean_chat_title("\n".join(text_parts))

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

    file_name = edit_file or read_file
    age = time.time() - mtime if mtime else 9999
    if age < 120 and edit_file:
        activity = "Редактирует файл"
    elif age < 120 and chat:
        activity = "Чат с AI"
    elif file_name:
        activity = "Редактирует файл"
    elif chat:
        activity = "Чат с AI"
    else:
        activity = "В Cursor"

    if not chat:
        chat = path.stem[:8]
    return chat, file_name, activity, mtime


class CursorWatcher:
    def __init__(self) -> None:
        self._state = CursorState()

    @property
    def state(self) -> CursorState:
        return self._state

    def refresh(self) -> CursorState:
        running = is_cursor_running()
        ws_name, ws_path = _workspace_info()
        chat, file_name, activity, _mt = "", "", "В Cursor", 0.0
        if running:
            project = _project_dir(ws_path)
            transcript = _newest_transcript(project)
            if transcript is None:
                transcript = _newest_transcript(None)
            if transcript is not None:
                chat, file_name, activity, _mt = _parse_transcript(transcript)

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
