"""Live Cursor state: focused chat, workspace, AI activity."""

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

USER_QUERY_RE = re.compile(
    r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL | re.IGNORECASE
)
TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>", re.DOTALL | re.IGNORECASE)

EDIT_TOOLS = {"Write", "StrReplace", "EditNotebook", "Delete"}
READ_TOOLS = {"Read", "Grep", "Glob"}
SHELL_TOOLS = {"Shell"}
SEARCH_TOOLS = {"WebSearch", "WebFetch", "Task", "CallDynamicTool", "GetDynamicTools"}

GLOBAL_STATE = (
    Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
)
CONVERSATION_DB = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "Cursor"
    / "User"
    / "globalStorage"
    / "conversation-search.db"
)
AI_TRACKING_DB = Path.home() / ".cursor" / "ai-tracking" / "ai-code-tracking.db"
PROJECTS = Path.home() / ".cursor" / "projects"


@dataclass
class CursorState:
    running: bool = False
    workspace: str = ""
    workspace_path: str = ""
    chat_name: str = ""
    activity: str = "В Cursor"
    agent_id: str = ""
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


def _selected_agent_id() -> str:
    if not GLOBAL_STATE.exists():
        return ""
    try:
        con = sqlite3.connect(f"file:{GLOBAL_STATE}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key=?",
                ("cursor/glass.selectedAgent",),
            ).fetchone()
            if row and str(row[0]).strip():
                return str(row[0]).strip().strip('"')
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key=?",
                ("cursor/glass.lastRealAgent",),
            ).fetchone()
            if row and str(row[0]).strip():
                return str(row[0]).strip().strip('"')
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        pass
    return ""


def _transcript_for_agent(agent_id: str) -> Optional[Path]:
    if not agent_id or not PROJECTS.exists():
        return None
    direct = list(PROJECTS.glob(f"**/agent-transcripts/{agent_id}/{agent_id}.jsonl"))
    if direct:
        return max(direct, key=lambda p: p.stat().st_mtime)
    loose = list(PROJECTS.glob(f"**/agent-transcripts/**/{agent_id}.jsonl"))
    if loose:
        return max(loose, key=lambda p: p.stat().st_mtime)
    return None


def _newest_transcript() -> Optional[Path]:
    if not PROJECTS.exists():
        return None
    newest: Optional[Path] = None
    newest_mtime = 0.0
    try:
        for f in PROJECTS.rglob("*.jsonl"):
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


def _workspace_from_project(project: Path) -> tuple[str, str]:
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


def _chat_title(agent_id: str) -> str:
    if not agent_id or not CONVERSATION_DB.exists():
        return ""
    try:
        con = sqlite3.connect(f"file:{CONVERSATION_DB}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT title FROM conversations WHERE id=? LIMIT 1",
                (agent_id,),
            ).fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return ""
    if not row:
        return ""
    title = _clean_title(str(row[0] or ""))
    return title


def _tracking_for_agent(agent_id: str) -> tuple[str, str, str]:
    """Return (workspace_name, workspace_path, latest_file) from ai-code-tracking."""
    if not agent_id or not AI_TRACKING_DB.exists():
        return "", "", ""
    try:
        con = sqlite3.connect(f"file:{AI_TRACKING_DB}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT fileName FROM ai_code_hashes "
                "WHERE conversationId=? ORDER BY timestamp DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return "", "", ""

    if not row or not row[0]:
        return "", "", ""

    raw = str(row[0]).lstrip("/")
    path = Path(raw)
    # fileName looks like /C:/Users/.../file.py
    if len(raw) >= 3 and raw[1] == ":":
        path = Path(raw)
    elif raw.startswith("C:/") or raw.startswith("c:/") or raw.startswith("D:/") or raw.startswith("d:/"):
        path = Path(raw)
    else:
        path = Path(raw)

    file_name = path.name
    parts = path.parts
    ws_path = ""
    # Prefer …/Documents/<project> or …/Projects/<project>
    for i, part in enumerate(parts):
        if part.lower() in {"documents", "projects"} and i + 1 < len(parts):
            ws_path = str(Path(*parts[: i + 2]))
            break
    if not ws_path:
        for parent in path.parents:
            if (parent / ".git").exists() or (parent / "run.py").exists():
                ws_path = str(parent)
                break
    if not ws_path:
        ws_path = str(path.parent)
    return Path(ws_path).name, ws_path, file_name


def _clean_title(raw: str) -> str:
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
    return _clean_title("\n".join(parts)) if parts else ""


def _fname(inp: dict[str, Any]) -> str:
    raw = inp.get("path") or inp.get("target_file") or ""
    if isinstance(raw, str) and raw.strip():
        return Path(raw.replace("\\", "/")).name
    return ""


def _activity_from_tools(kind: str, file_name: str) -> str:
    if kind == "editing" and file_name:
        return f"Редактирует {file_name}"
    if kind == "reading" and file_name:
        return f"Читает {file_name}"
    if kind == "shell":
        return "Выполняет команды"
    if kind == "search":
        return "Ищет информацию"
    if kind == "thinking":
        return "Думает…"
    if kind == "chatting":
        return "Отвечает в чате"
    return "В Cursor"


def _parse_transcript(path: Path) -> tuple[str, str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > 300_000:
                fh.seek(-300_000, 2)
                tail = fh.read().decode("utf-8", errors="ignore").split("\n", 1)[-1]
            else:
                tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return "", "В Cursor"

    last_user = ""
    first_user = ""
    kind = "idle"
    file_name = ""

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
                if not first_user:
                    first_user = title
                last_user = title
                kind = "chatting"

        for part in _message_parts(obj):
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype in ("thinking", "reasoning"):
                kind = "thinking"
                continue
            if ptype != "tool_use":
                continue
            name = str(part.get("name") or "")
            inp = part.get("input") or {}
            if not isinstance(inp, dict):
                inp = {}
            fname = _fname(inp)

            if name in EDIT_TOOLS:
                kind = "editing"
                if fname:
                    file_name = fname
            elif name in READ_TOOLS:
                kind = "reading"
                if fname:
                    file_name = fname
            elif name in SHELL_TOOLS:
                kind = "shell"
            elif name in SEARCH_TOOLS:
                kind = "search"
            elif name:
                kind = "chatting"

    return first_user or last_user, _activity_from_tools(kind, file_name)


class CursorWatcher:
    def __init__(self) -> None:
        self._state = CursorState()

    @property
    def state(self) -> CursorState:
        return self._state

    def refresh(self) -> CursorState:
        running = is_cursor_running()
        workspace, ws_path, chat, activity, agent_id = "", "", "", "В Cursor", ""

        if running:
            agent_id = _selected_agent_id()
            transcript: Optional[Path] = None
            if agent_id:
                transcript = _transcript_for_agent(agent_id)
            else:
                transcript = _newest_transcript()
                if transcript is not None:
                    agent_id = transcript.stem

            track_ws, track_path, track_file = (
                _tracking_for_agent(agent_id) if agent_id else ("", "", "")
            )

            # Only parse transcript that belongs to the focused agent
            if transcript is not None:
                project = _project_from_transcript(transcript)
                if project is not None and not track_ws:
                    workspace, ws_path = _workspace_from_project(project)
                chat, activity = _parse_transcript(transcript)

            if track_ws:
                workspace = track_ws
                ws_path = track_path or ws_path

            if track_file and (
                not transcript
                or activity
                in ("В Cursor", "Отвечает в чате", "Думает…", "Ожидает чат", "idle")
            ):
                activity = f"Редактирует {track_file}"

            title = _chat_title(agent_id) if agent_id else ""
            if title:
                chat = title
            elif not chat:
                chat = "Активный чат" if agent_id else ""
            if not activity:
                activity = "В Cursor"

        self._state = CursorState(
            running=running,
            workspace=workspace,
            workspace_path=ws_path,
            chat_name=chat,
            activity=activity,
            agent_id=agent_id,
            updated_at=time.time(),
        )
        return self._state
