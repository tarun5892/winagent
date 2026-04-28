"""Block destructive shell ops; gate execution on user confirmation."""
from __future__ import annotations

import re
from collections.abc import Callable

from . import coding_tools
from .logger import get_logger
from .schema import (
    Action,
    ApplyPatchAction,
    FileDeleteAction,
    FileEditAction,
    FileReadAction,
    FileWriteAction,
    FindFilesAction,
    GrepAction,
    ListDirAction,
    PowerShellAction,
    ShellAction,
)

log = get_logger("safety")

_BLOCKED_PATTERNS = [
    r"\bRemove-Item\b[^\n]*-Recurse",
    r"\bRemove-Item\b[^\n]*-Force",
    r"\bFormat-Volume\b",
    r"\bClear-Disk\b",
    r"\bStop-Computer\b",
    r"\bRestart-Computer\b",
    r"\bReg(?:istry)?\s+delete\b",
    r"\b(?:rd|rmdir)\s+/s\b",
    r"\bdel\s+/[sf]\b",
    r"\bshutdown\b",
    r"\bdiskpart\b",
    r"(?:Iex|Invoke-Expression)\b[^\n]*(?:Net\.WebClient|Invoke-WebRequest|curl|wget)",
]
_BLOCK_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)

ConfirmFn = Callable[[str], bool]

# Read-only actions never need confirmation, even when confirmation mode is on.
_READ_ONLY_TYPES: tuple[type, ...] = (
    FileReadAction,
    ListDirAction,
    GrepAction,
    FindFilesAction,
)


class SafetyLayer:
    def __init__(self, confirm_fn: ConfirmFn, confirmation_mode: bool = True) -> None:
        self._confirm = confirm_fn
        self.confirmation_mode = confirmation_mode

    def filter(self, actions: list[Action]) -> tuple[list[Action], list[str]]:
        """Return ``(allowed_actions, rejection_reasons)``."""
        allowed: list[Action] = []
        rejects: list[str] = []
        for a in actions:
            reason = self._reject_reason(a)
            if reason is not None:
                log.warning(reason)
                rejects.append(reason)
                continue
            allowed.append(a)
        return allowed, rejects

    @staticmethod
    def _reject_reason(a: Action) -> str | None:
        if isinstance(a, PowerShellAction) and _BLOCK_RE.search(a.command):
            return f"Blocked destructive PowerShell: {a.command[:80]}"
        if isinstance(a, ShellAction) and coding_tools.is_shell_destructive(a.command):
            return f"Blocked destructive shell: {a.command[:80]}"
        return None

    def confirm_plan(self, actions: list[Action]) -> bool:
        if not self.confirmation_mode or not actions:
            return True
        # If every action is read-only, skip the dialog entirely.
        if all(isinstance(a, _READ_ONLY_TYPES) for a in actions):
            return True
        summary_lines = [f"• {a.model_dump()}" for a in actions[:15]]
        if len(actions) > 15:
            summary_lines.append(f"• …(+{len(actions) - 15} more)")
        return self._confirm("\n".join(summary_lines))

    @staticmethod
    def is_read_only(a: Action) -> bool:
        return isinstance(a, _READ_ONLY_TYPES)

    @staticmethod
    def is_destructive(a: Action) -> bool:
        if isinstance(a, FileDeleteAction):
            return True
        if isinstance(a, ShellAction):
            return coding_tools.is_shell_destructive(a.command)
        if isinstance(a, PowerShellAction):
            return bool(_BLOCK_RE.search(a.command))
        return False

    @staticmethod
    def is_mutating(a: Action) -> bool:
        return isinstance(
            a,
            (
                FileWriteAction,
                FileEditAction,
                FileDeleteAction,
                ApplyPatchAction,
            ),
        )
