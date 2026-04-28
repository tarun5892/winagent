"""Block destructive shell ops; gate execution on user confirmation."""
from __future__ import annotations

import re
from collections.abc import Callable

from .logger import get_logger
from .schema import Action, PowerShellAction

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


class SafetyLayer:
    def __init__(self, confirm_fn: ConfirmFn, confirmation_mode: bool = True) -> None:
        self._confirm = confirm_fn
        self.confirmation_mode = confirmation_mode

    def filter(self, actions: list[Action]) -> tuple[list[Action], list[str]]:
        """Return ``(allowed_actions, rejection_reasons)``."""
        allowed: list[Action] = []
        rejects: list[str] = []
        for a in actions:
            if isinstance(a, PowerShellAction) and _BLOCK_RE.search(a.command):
                msg = f"Blocked destructive PowerShell: {a.command[:80]}"
                log.warning(msg)
                rejects.append(msg)
                continue
            allowed.append(a)
        return allowed, rejects

    def confirm_plan(self, actions: list[Action]) -> bool:
        if not self.confirmation_mode or not actions:
            return True
        summary_lines = [f"• {a.model_dump()}" for a in actions[:15]]
        if len(actions) > 15:
            summary_lines.append(f"• …(+{len(actions) - 15} more)")
        return self._confirm("\n".join(summary_lines))
