"""Live Cursor state from composerData + bubbleId toolFormerData."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .i18n import normalize_lang, t

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

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

# Cursor bubble toolFormerData.name → activity kind
TOOL_KIND = {
    "edit_file_v2": "editing",
    "edit_file": "editing",
    "search_replace": "editing",
    "write": "editing",
    "apply_patch": "editing",
    "read_file_v2": "reading",
    "read_file": "reading",
    "ripgrep_raw_search": "search",
    "grep": "search",
    "glob_file_search": "search",
    "file_search": "search",
    "run_terminal_command_v2": "shell",
    "run_terminal_cmd": "shell",
    "shell": "shell",
    "web_search": "search",
    "web_fetch": "search",
    "get_mcp_tools": "search",
    "call_mcp_tool": "search",
    "task_v2": "chatting",
    "todo_write": "chatting",
    "create_plan": "chatting",
    "update_current_step": "chatting",
    "search_conversations": "search",
}

LOADING_STATUSES = {"loading", "pending", "running", "in_progress"}
DONE_COMPOSER = {"completed", "aborted", "none", ""}


@dataclass
class CursorState:
    running: bool = False
    workspace: str = ""
    workspace_path: str = ""
    chat_name: str = ""
    activity: str = ""
    kind: str = "idle"
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
    unfinished_run_ms: float = 0.0
    subtitle: str = ""


@dataclass
class _BubbleAct:
    kind: str = "idle"
    file_name: str = ""
    tool_name: str = ""
    tool_status: str = ""
    active: bool = False
    age_sec: float = 1e9


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


def _open_state() -> Optional[sqlite3.Connection]:
    if not GLOBAL_STATE.exists():
        return None
    try:
        # Read-write avoids stale WAL snapshots on some SQLite builds
        return sqlite3.connect(str(GLOBAL_STATE), timeout=0.4)
    except sqlite3.Error:
        try:
            return sqlite3.connect(f"file:{GLOBAL_STATE}?mode=ro", uri=True, timeout=0.4)
        except sqlite3.Error:
            return None


def _selected_agent_id() -> str:
    con = _open_state()
    if con is None:
        return ""
    try:
        for key in ("cursor/glass.selectedAgent", "cursor/glass.lastRealAgent"):
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key=?", (key,)
            ).fetchone()
            if row and str(row[0]).strip():
                return str(row[0]).strip().strip('"')
    except sqlite3.Error:
        return ""
    finally:
        con.close()
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
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(x) for x in node)
        return False

    return walk(data)


def _composer_meta(agent_id: str) -> _ComposerMeta:
    out = _ComposerMeta()
    if not agent_id:
        return out
    con = _open_state()
    if con is None:
        return out
    try:
        row = con.execute(
            "SELECT value FROM cursorDiskKV WHERE key=?",
            (f"composerData:{agent_id}",),
        ).fetchone()
    except sqlite3.Error:
        con.close()
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
    if not row:
        return out
    try:
        data = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return out

    out.name = str(data.get("name") or "").strip()
    out.subtitle = str(data.get("subtitle") or "").strip()
    out.status = str(data.get("status") or "").strip().lower()
    bubbles = data.get("generatingBubbleIds") or []
    out.generating = bool(
        out.status == "generating"
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
    try:
        out.unfinished_run_ms = float(data.get("unfinishedRunAt") or 0)
    except (TypeError, ValueError):
        out.unfinished_run_ms = 0.0

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


def _parse_created_at(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val / 1000.0 if val > 1e12 else val
    text = str(raw).strip()
    if not text:
        return 0.0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _file_from_tool_args(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in (
        "relativeWorkspacePath",
        "path",
        "target_file",
        "filePath",
        "file_path",
        "targetDirectory",
    ):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return Path(val.replace("\\", "/")).name
    return ""


def _kind_from_tool(name: str) -> str:
    key = (name or "").strip()
    if key in TOOL_KIND:
        return TOOL_KIND[key]
    low = key.lower()
    if "edit" in low or "write" in low or "replace" in low:
        return "editing"
    if "read" in low:
        return "reading"
    if "terminal" in low or "shell" in low or "command" in low:
        return "shell"
    if "grep" in low or "ripgrep" in low or "search" in low or "glob" in low or "web" in low:
        return "search"
    return "chatting"


def _bubble_activity(agent_id: str) -> _BubbleAct:
    """Primary activity signal: Cursor bubbleId + toolFormerData."""
    out = _BubbleAct()
    if not agent_id:
        return out
    con = _open_state()
    if con is None:
        return out
    now = time.time()
    try:
        rows = con.execute(
            "SELECT value FROM cursorDiskKV WHERE key LIKE ? ORDER BY rowid DESC LIMIT 80",
            (f"bubbleId:{agent_id}:%",),
        ).fetchall()
    except sqlite3.Error:
        con.close()
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass

    loading: Optional[_BubbleAct] = None
    latest_tool: Optional[_BubbleAct] = None
    latest_thinking_age = 1e9
    latest_text_age = 1e9
    newest_age = 1e9
    rank = 0

    for (raw,) in rows:
        try:
            b = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(b, dict):
            continue

        created = _parse_created_at(b.get("createdAt"))
        # rowid DESC order ≈ recency; missing createdAt → use rank as soft age
        age = (now - created) if created else float(rank)
        newest_age = min(newest_age, age)
        rank += 1

        # Thinking bubble (capabilityType 30)
        if b.get("capabilityType") == 30 or b.get("thinking"):
            latest_thinking_age = min(latest_thinking_age, age)

        text = str(b.get("text") or "").strip()
        if b.get("type") == 2 and text:
            latest_text_age = min(latest_text_age, age)

        td = b.get("toolFormerData")
        if not isinstance(td, dict) or not td.get("name"):
            continue

        name = str(td.get("name") or "")
        status = str(td.get("status") or "").lower()
        args = str(td.get("params") or td.get("rawArgs") or "")
        fname = _file_from_tool_args(args)
        kind = _kind_from_tool(name)
        act = _BubbleAct(
            kind=kind,
            file_name=fname,
            tool_name=name,
            tool_status=status,
            active=status in LOADING_STATUSES,
            age_sec=age,
        )
        if latest_tool is None:
            latest_tool = act
        if status in LOADING_STATUSES and loading is None:
            loading = act

    if loading is not None:
        loading.active = True
        return loading

    # Still in a turn: recent thinking / streaming text / fresh bubbles
    turn_hot = newest_age <= 10.0 or latest_thinking_age <= 8.0
    if turn_hot and latest_thinking_age <= 8.0 and (
        latest_tool is None or latest_thinking_age <= (latest_tool.age_sec + 0.5)
    ):
        return _BubbleAct(kind="thinking", active=True, age_sec=latest_thinking_age)

    if turn_hot and latest_tool is not None and latest_tool.age_sec <= 30.0:
        latest_tool.active = True
        return latest_tool

    if turn_hot and latest_text_age <= 8.0:
        return _BubbleAct(kind="chatting", active=True, age_sec=latest_text_age)

    if latest_tool is not None and latest_tool.age_sec <= 5.0:
        latest_tool.active = True
        return latest_tool

    return out


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
    text = re.sub(r"\s+", " ", str(row[0] or "")).strip()
    if len(text) > 48:
        text = text[:45].rstrip() + "…"
    return text


def _tracking_workspace(agent_id: str) -> tuple[str, str]:
    if not agent_id or not AI_TRACKING_DB.exists():
        return "", ""
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
        return "", ""
    if not row or not row[0]:
        return "", ""
    raw = str(row[0]).lstrip("/")
    path = Path(raw)
    parts = path.parts
    for i, part in enumerate(parts):
        if part.lower() in {"documents", "projects"} and i + 1 < len(parts):
            ws = Path(*parts[: i + 2])
            return ws.name, str(ws)
    return path.parent.name, str(path.parent)


def _workspace_from_project_id(project_name: str) -> tuple[str, str]:
    root = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    pid = project_name.lower()
    if not root.exists():
        return project_name.replace("-", " "), ""
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
    except OSError:
        pass
    return project_name.replace("-", " "), ""


def _workspace_fallback(agent_id: str) -> tuple[str, str]:
    track = _tracking_workspace(agent_id)
    if track[0]:
        return track
    if not agent_id or not PROJECTS.exists():
        return "", ""
    # Prefer project folder that owns this agent's transcript
    hits = list(PROJECTS.glob(f"**/agent-transcripts/{agent_id}"))
    if hits:
        project = hits[0].parent.parent
        return _workspace_from_project_id(project.name)
    return "", ""


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
        self._lang = "en"

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
            bubble = _bubble_activity(agent_id) if agent_id else _BubbleAct()

            if meta.workspace_path:
                ws_path = meta.workspace_path
                workspace = Path(ws_path).name
            else:
                workspace, ws_path = _workspace_fallback(agent_id)

            now = time.time()
            unfinished_age = (
                now - meta.unfinished_run_ms / 1000.0 if meta.unfinished_run_ms else 1e9
            )
            composer_hot = meta.generating or unfinished_age <= 15.0

            # 1) Live tool (status=loading) or fresh bubble activity
            if bubble.active and bubble.kind != "idle":
                kind = bubble.kind
            # 2) Typing a prompt (never expose text)
            elif meta.has_draft and not composer_hot and not bubble.active:
                kind = "typing"
            # 3) Composer still hot (unfinishedRun / generating)
            elif composer_hot:
                if bubble.kind != "idle":
                    kind = bubble.kind
                elif meta.subtitle.lower().startswith("edited"):
                    kind = "editing"
                else:
                    kind = "chatting"
            # 4) Idle — do not keep stale Reading forever
            else:
                kind = "idle"

            file_name = bubble.file_name if kind in ("editing", "reading", "search") else ""
            if kind == "search":
                # Searching doesn't need file in label, but keep if useful
                pass
            if kind == "editing" and not file_name and meta.subtitle:
                # subtitle like "Edited a.py, b.py"
                m = re.search(r"([\w.-]+\.\w+)", meta.subtitle)
                if m:
                    file_name = m.group(1)
            chat = meta.name or _chat_title(agent_id) or ""
            if not chat:
                chat = t(lang, "chat_fallback") if agent_id else ""
            activity = _activity_label(lang, kind, file_name)
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
