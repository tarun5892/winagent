"""Rolling short-term memory injected into the Gemini prompt."""
from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Any

from .config import CONFIG


class MemoryManager:
    """Bounded, thread-safe short-term memory.

    Tracks the last N user commands, the last N executed action summaries,
    a free-form ``current_goal`` and ``notes`` field. Snapshots are JSON-safe
    so they can be embedded directly in an LLM prompt.
    """

    def __init__(self, window: int = CONFIG.memory_window) -> None:
        if window < 1:
            raise ValueError("memory window must be >= 1")
        self._window = window
        self._commands: deque[str] = deque(maxlen=window)
        self._actions: deque[dict[str, Any]] = deque(maxlen=window)
        self._goal: str | None = None
        self._notes: str | None = None
        self._lock = RLock()

    def add_command(self, cmd: str) -> None:
        with self._lock:
            self._commands.append(cmd.strip())

    def add_actions(self, actions: list[dict[str, Any]]) -> None:
        with self._lock:
            for a in actions:
                self._actions.append(self._summarize(a))

    def update(self, memory_update: dict[str, Any] | None) -> None:
        if not memory_update:
            return
        with self._lock:
            goal = memory_update.get("current_goal")
            if goal:
                self._goal = str(goal)[:256]
            notes = memory_update.get("notes")
            if notes:
                self._notes = str(notes)[:512]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "recent_commands": list(self._commands),
                "recent_actions": list(self._actions),
                "current_goal": self._goal,
                "notes": self._notes,
            }

    def reset(self) -> None:
        with self._lock:
            self._commands.clear()
            self._actions.clear()
            self._goal = None
            self._notes = None

    @staticmethod
    def _summarize(action: dict[str, Any]) -> dict[str, Any]:
        t = action.get("type", "?")
        if t == "type":
            txt = str(action.get("text", ""))
            return {
                "type": "type",
                "text": txt[:60] + ("…" if len(txt) > 60 else ""),
            }
        if t == "powershell":
            cmd = str(action.get("command", ""))
            return {"type": "powershell", "command": cmd[:80]}
        if t == "shell":
            cmd = str(action.get("command", ""))
            return {"type": "shell", "command": cmd[:120]}
        if t == "excel":
            return {
                "type": "excel",
                "operation": action.get("operation"),
                "cell": action.get("cell"),
                "sheet": action.get("sheet"),
            }
        if t in ("file_read", "file_delete", "list_dir"):
            return {"type": t, "path": action.get("path")}
        if t == "file_write":
            content = str(action.get("content", ""))
            return {
                "type": "file_write",
                "path": action.get("path"),
                "size": len(content),
            }
        if t == "file_edit":
            return {"type": "file_edit", "path": action.get("path")}
        if t == "apply_patch":
            edits = action.get("edits") or []
            return {
                "type": "apply_patch",
                "path": action.get("path"),
                "edits": len(edits),
            }
        if t == "grep":
            return {
                "type": "grep",
                "pattern": str(action.get("pattern", ""))[:60],
                "path": action.get("path"),
            }
        if t == "find_files":
            return {
                "type": "find_files",
                "pattern": str(action.get("pattern", ""))[:60],
            }
        return action
