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

from .i18n import normalize_lang, t

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

# Composer statuses that mean the agent is actively working
GENERATING_STATUSES = {
    "generating",
    "applying",
    "running",
    "in_progress",
    "streaming",
    "working",
}

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

# After AI stops, ignore stale tool traces older than this
STALE_TOOL_SEC = 25.0


@dataclass
class CursorState:
    running: bool = False
    workspace: str = ""
    workspace_path: str = ""
    chat_name: str = ""
    activity: str = ""
    kind: str = "idle"  # idle | typing | editing | reading | shell | search | thinking | chatting
    agent_id: str = ""
    updated_at: float = field(default_factory=time.time)


@dataclass
class _ComposerMeta:
    name: str = ""
    status: str = ""
    generating: bool = False
    has_draft: bool = False
    workspace_path: str = ""
    last_updated_ms: float = 0.0


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
            for key in ("cursor/glass.selectedAgent", "cursor/glass.lastRealAgent"):
                row = con.execute(
                    "SELECT value FROM ItemTable WHERE key=?", (key,)
                ).fetchone()
                if row and str(row[0]).strip():
                    return str(row[0]).strip().strip('"')
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        pass
    return ""


def _rich_has_text(rich: str) -> bool:
    rich = (rich or "").strip()
    if not rich:
        return False
    try:
        data = json.loads(rich)
    except json.JSONDecodeError:
        return True

    def walk(node: Any) -> bool:
        if isinstance(node, str):
            return bool(node.strip())
        if isinstance(node, dict):
            if isinstance(node.get("text"), str) and node["text"].strip():
                return True
            for v in node.values():
                if walk(v):
                    return True
        if isinstance(node, list):
            return any(walk(x) for x in node)
        return False

    return walk(data)


def _composer_meta(agent_id: str) -> _ComposerMeta:
    out = _ComposerMeta()
    if not agent_id or not GLOBAL_STATE.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{GLOBAL_STATE}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT value FROM cursorDiskKV WHERE key=?",
                (f"composerData:{agent_id}",),
            ).fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return out
    if not row:
        return out
    try:
        data = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return out

    out.name = str(data.get("name") or "").strip()
    out.status = str(data.get("status") or "").strip().lower()
    bubbles = data.get("generatingBubbleIds") or []
    out.generating = bool(
        out.status in GENERATING_STATUSES
        or (isinstance(bubbles, list) and len(bubbles) > 0)
        or bool(data.get("isContinuationInProgress"))
    )
    text = str(data.get("text") or "")
    rich = str(data.get("richText") or "")
    out.has_draft = bool(text.strip()) or _rich_has_text(rich)
    try:
        out.last_updated_ms = float(data.get("lastUpdatedAt") or 0)
    except (TypeError, ValueError):
        out.last_updated_ms = 0.0

    ws = data.get("workspaceIdentifier") or {}
    if isinstance(ws, dict):
        uri = ws.get("uri") or {}
        if isinstance(uri, dict):
            folder = uri.get("fsPath") or uri.get("path") or ""
            if folder:
                out.workspace_path = str(folder)
        elif isinstance(uri, str) and uri.startswith("file:///"):
            out.workspace_path = _decode_file_uri(uri)
    return out


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
    return _clean_title(str(row[0] or ""))


def _tracking_for_agent(agent_id: str) -> tuple[str, str, str, float]:
    """Return (workspace_name, workspace_path, latest_file, timestamp_ms)."""
    if not agent_id or not AI_TRACKING_DB.exists():
        return "", "", "", 0.0
    try:
        con = sqlite3.connect(f"file:{AI_TRACKING_DB}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT fileName, timestamp FROM ai_code_hashes "
                "WHERE conversationId=? ORDER BY timestamp DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return "", "", "", 0.0

    if not row or not row[0]:
        return "", "", "", 0.0

    raw = str(row[0]).lstrip("/")
    try:
        ts = float(row[1] or 0)
    except (TypeError, ValueError):
        ts = 0.0
    path = Path(raw)
    file_name = path.name
    parts = path.parts
    ws_path = ""
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
    return Path(ws_path).name, ws_path, file_name, ts


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


def _parse_transcript(path: Path) -> tuple[str, str, str, float]:
    """Return (chat_from_query, kind, file_name, last_tool_mtime)."""
    try:
        st = path.stat()
        size = st.st_size
        mtime = st.st_mtime
        with path.open("rb") as fh:
            if size > 300_000:
                fh.seek(-300_000, 2)
                tail = fh.read().decode("utf-8", errors="ignore").split("\n", 1)[-1]
            else:
                tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return "", "idle", "", 0.0

    last_user = ""
    first_user = ""
    kind = "idle"
    file_name = ""
    last_action_age_hint = mtime

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
                file_name = ""

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

    return first_user or last_user, kind, file_name, last_action_age_hint


def _activity_label(lang: str, kind: str, file_name: str = "") -> str:
    if kind == "typing":
        return t(lang, "act_typing")
    if kind == "idle":
        return t(lang, "act_idle")
    if kind == "editing":
        return t(lang, "act_editing", file=file_name) if file_name else t(lang, "act_chatting")
    if kind == "reading":
        return t(lang, "act_reading", file=file_name) if file_name else t(lang, "act_chatting")
    if kind == "shell":
        return t(lang, "act_shell")
    if kind == "search":
        return t(lang, "act_search")
    if kind == "thinking":
        return t(lang, "act_thinking")
    if kind == "chatting":
        return t(lang, "act_chatting")
    return t(lang, "act_in_cursor")


class CursorWatcher:
    def __init__(self) -> None:
        self._state = CursorState()
        self._lang = "ru"

    def set_language(self, lang: str) -> None:
        self._lang = normalize_lang(lang)

    @property
    def state(self) -> CursorState:
        return self._state

    def refresh(self, lang: str | None = None) -> CursorState:
        if lang is not None:
            self._lang = normalize_lang(lang)
        lang = self._lang

        running = is_cursor_running()
        workspace, ws_path, chat, activity, agent_id = "", "", "", "", ""
        kind = "idle"

        if running:
            agent_id = _selected_agent_id()
            meta = _composer_meta(agent_id) if agent_id else _ComposerMeta()

            transcript: Optional[Path] = None
            if agent_id:
                transcript = _transcript_for_agent(agent_id)
            else:
                transcript = _newest_transcript()
                if transcript is not None:
                    agent_id = transcript.stem
                    meta = _composer_meta(agent_id)

            track_ws, track_path, track_file, track_ts = (
                _tracking_for_agent(agent_id) if agent_id else ("", "", "", 0.0)
            )

            tool_kind, tool_file, tool_mtime = "idle", "", 0.0
            if transcript is not None:
                project = _project_from_transcript(transcript)
                if project is not None and not track_ws and not meta.workspace_path:
                    workspace, ws_path = _workspace_from_project(project)
                _q, tool_kind, tool_file, tool_mtime = _parse_transcript(transcript)

            if meta.workspace_path:
                ws_path = meta.workspace_path
                workspace = Path(ws_path).name
            elif track_ws:
                workspace = track_ws
                ws_path = track_path

            now = time.time()
            track_fresh = bool(track_ts) and (now - (track_ts / 1000.0)) <= STALE_TOOL_SEC

            # 1) User typing a prompt (never expose the text)
            if meta.has_draft and not meta.generating:
                kind = "typing"
                tool_file = ""
            # 2) AI actively working — only then show tool activity
            elif meta.generating:
                if tool_kind in ("editing", "reading", "shell", "search", "thinking", "chatting"):
                    kind = tool_kind
                elif track_fresh and track_file:
                    kind = "editing"
                    tool_file = track_file
                else:
                    kind = "chatting"
                    tool_file = ""
            # 3) Idle — never keep stale "shell/editing" after the run ends
            else:
                kind = "idle"
                tool_file = ""

            chat = meta.name or _chat_title(agent_id) or ""
            if not chat:
                chat = t(lang, "chat_fallback") if agent_id else ""

            activity = _activity_label(lang, kind, tool_file)

        else:
            activity = t(lang, "act_in_cursor")

        self._state = CursorState(
            running=running,
            workspace=workspace,
            workspace_path=ws_path,
            chat_name=chat,
            activity=activity,
            kind=kind,
            agent_id=agent_id,
            updated_at=time.time(),
        )
        return self._state
