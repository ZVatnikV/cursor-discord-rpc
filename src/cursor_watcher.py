"""Live Cursor state from the newest agent transcript."""

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
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".ps1", ".css",
    ".html", ".cs", ".go", ".rs", ".java", ".cpp", ".h", ".yml", ".yaml",
    ".toml", ".txt",
}
SKIP_DIR_NAMES = {
    ".git", "dist", "build", "node_modules", "__pycache__", ".venv", "venv", ".cursor",
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


@dataclass
class _Parsed:
    chat_latest: str = ""
    file_name: str = ""
    kind: str = "idle"  # editing | reading | chatting | shell | idle
    transcript_mtime: float = 0.0


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


def _newest_transcript() -> Optional[Path]:
    base = Path.home() / ".cursor" / "projects"
    if not base.exists():
        return None
    newest: Optional[Path] = None
    newest_mtime = 0.0
    try:
        for f in base.rglob("*.jsonl"):
            if "agent-transcripts" not in f.parts:
                continue
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if m > newest_mtime:
                newest_mtime, newest = m, f
    except OSError:
        return None
    return newest


def _project_from_transcript(transcript: Path) -> Optional[Path]:
    for parent in transcript.parents:
        if parent.name == "agent-transcripts":
            return parent.parent
    return None


def _workspace_path_from_project(project: Path) -> tuple[str, str]:
    root = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    pid = project.name.lower()
    if root.exists():
        try:
            for d in root.iterdir():
                wj = d / "workspace.json"
                if not wj.exists():
                    continue
                try:
                    data = json.loads(wj.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                folder = data.get("folder") or ""
                if not (isinstance(folder, str) and folder.startswith("file:///")):
                    continue
                full = _decode_file_uri(folder)
                encoded = re.sub(r"[^A-Za-z0-9]+", "-", full).strip("-").lower()
                if encoded == pid or pid in encoded or encoded in pid:
                    return Path(full).name, full
                if Path(full).name.lower().replace(" ", "-") in pid:
                    return Path(full).name, full
        except OSError:
            pass

    name = project.name
    for prefix in (
        "c-Users-admin-Documents-",
        "C-Users-admin-Documents-",
        "d-SteamLibrary-steamapps-common-",
    ):
        if name.lower().startswith(prefix.lower()):
            name = name[len(prefix) :]
            break
    return name.replace("-", " "), ""


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


def _user_text(obj: dict[str, Any]) -> str:
    parts = [
        str(p.get("text") or "")
        for p in _message_parts(obj)
        if isinstance(p, dict) and p.get("type") == "text"
    ]
    return _clean_chat_title("\n".join(parts)) if parts else ""


def _parse_transcript(path: Path) -> _Parsed:
    out = _Parsed()
    try:
        out.transcript_mtime = path.stat().st_mtime
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > 250_000:
                fh.seek(-250_000, 2)
                tail = fh.read().decode("utf-8", errors="ignore").split("\n", 1)[-1]
            else:
                tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return out

    last_edit = ""
    last_read = ""
    last_kind = "idle"
    last_user = ""

    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        role = str(obj.get("role") or "").lower()
        if role in ("user", "human"):
            title = _user_text(obj)
            if title:
                last_user = title
                last_kind = "chatting"

        for part in _message_parts(obj):
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            name = str(part.get("name") or "")
            inp = part.get("input") or {}
            if not isinstance(inp, dict):
                continue
            raw_path = inp.get("path") or inp.get("target_file") or ""
            fname = ""
            if isinstance(raw_path, str) and raw_path.strip():
                fname = Path(raw_path.replace("\\", "/")).name

            if name in EDIT_TOOLS and fname and "." in fname:
                last_edit = fname
                last_kind = "editing"
            elif name in READ_TOOLS and fname and "." in fname:
                last_read = fname
                last_kind = "reading"
            elif name == "Shell":
                last_kind = "shell"
            elif name and last_kind not in ("editing", "reading"):
                last_kind = "chatting"

    out.chat_latest = last_user
    # File only when the latest action was actually a file tool
    if last_kind == "editing":
        out.file_name = last_edit
    elif last_kind == "reading":
        out.file_name = last_read or last_edit
    else:
        out.file_name = ""
    out.kind = last_kind
    return out


def _recent_workspace_file(workspace_path: str, max_age_sec: float = 120) -> tuple[str, float]:
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


def _activity_label(kind: str) -> str:
    return {
        "editing": "Редактирует файл",
        "reading": "Читает файл",
        "shell": "Выполняет команды",
        "chatting": "Чат с AI",
    }.get(kind, "В Cursor")


class CursorWatcher:
    def __init__(self) -> None:
        self._state = CursorState()

    @property
    def state(self) -> CursorState:
        return self._state

    def refresh(self) -> CursorState:
        running = is_cursor_running()
        ws_name, ws_path = "", ""
        chat, file_name, activity = "", "", "В Cursor"

        if running:
            transcript = _newest_transcript()
            parsed = _Parsed()
            if transcript is not None:
                project = _project_from_transcript(transcript)
                if project is not None:
                    ws_name, ws_path = _workspace_path_from_project(project)
                parsed = _parse_transcript(transcript)

            disk_file, disk_mtime = _recent_workspace_file(ws_path)
            kind = parsed.kind
            file_name = parsed.file_name

            # Manual/disk edit wins only if newer than transcript
            if disk_file and disk_mtime > (parsed.transcript_mtime or 0):
                file_name = disk_file
                kind = "editing"

            chat = parsed.chat_latest
            activity = _activity_label(kind)

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
