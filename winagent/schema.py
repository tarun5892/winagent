"""Strict action schema. Single source of truth for the LLM contract."""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClickAction(_StrictModel):
    type: Literal["click"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    button: Literal["left", "right", "middle"] = "left"
    clicks: int = Field(default=1, ge=1, le=3)


class MoveAction(_StrictModel):
    type: Literal["move"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class TypeAction(_StrictModel):
    type: Literal["type"]
    text: str = Field(max_length=4000)
    interval_ms: int = Field(default=15, ge=0, le=200)


class HotkeyAction(_StrictModel):
    type: Literal["hotkey"]
    keys: list[str] = Field(min_length=1, max_length=5)


class ScrollAction(_StrictModel):
    type: Literal["scroll"]
    dy: int


class WaitAction(_StrictModel):
    type: Literal["wait"]
    ms: int = Field(ge=0, le=10_000)


class PowerShellAction(_StrictModel):
    type: Literal["powershell"]
    command: str = Field(max_length=2000)


class ExcelAction(_StrictModel):
    type: Literal["excel"]
    operation: Literal[
        "open", "close", "save", "save_as",
        "write_cell", "read_cell", "write_range",
        "add_sheet", "select_sheet", "run_vba",
    ]
    path: str | None = None
    sheet: str | None = None
    cell: str | None = None
    value: str | None = None
    range: str | None = None
    values: list[list[str]] | None = None
    vba_code: str | None = None


class ScreenshotAction(_StrictModel):
    type: Literal["screenshot"]


# ---- Coding-agent actions -------------------------------------------------
class FileReadAction(_StrictModel):
    """Read a file (or a slice of lines)."""

    type: Literal["file_read"]
    path: str = Field(min_length=1, max_length=4096)
    offset: int = Field(default=0, ge=0)  # 0-based line offset
    limit: int | None = Field(default=None, ge=1, le=10_000)
    max_bytes: int = Field(default=200_000, ge=1, le=4_000_000)


class FileWriteAction(_StrictModel):
    """Overwrite (or create) a file with ``content``."""

    type: Literal["file_write"]
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(default="", max_length=2_000_000)
    create_dirs: bool = True


class FileEditAction(_StrictModel):
    """Find/replace inside an existing file. ``old_string`` must be unique
    unless ``replace_all`` is true."""

    type: Literal["file_edit"]
    path: str = Field(min_length=1, max_length=4096)
    old_string: str = Field(min_length=1, max_length=200_000)
    new_string: str = Field(default="", max_length=200_000)
    replace_all: bool = False


class FileDeleteAction(_StrictModel):
    """Delete a single file. Directories must be removed via ``shell``
    (and are blocked unless explicitly approved)."""

    type: Literal["file_delete"]
    path: str = Field(min_length=1, max_length=4096)


class ListDirAction(_StrictModel):
    type: Literal["list_dir"]
    path: str = Field(min_length=1, max_length=4096)
    recursive: bool = False
    max_entries: int = Field(default=200, ge=1, le=5000)


class ApplyPatchAction(_StrictModel):
    """Apply one or more sequential ``old_string -> new_string`` edits to a
    file atomically. This is the preferred way to modify code."""

    class _Edit(_StrictModel):
        old_string: str = Field(min_length=1, max_length=200_000)
        new_string: str = Field(default="", max_length=200_000)
        replace_all: bool = False

    type: Literal["apply_patch"]
    path: str = Field(min_length=1, max_length=4096)
    edits: list[_Edit] = Field(min_length=1, max_length=64)


class ShellAction(_StrictModel):
    """Run a cross-platform shell command. ``cwd`` is resolved against the
    orchestrator's project root."""

    type: Literal["shell"]
    command: str = Field(min_length=1, max_length=4000)
    cwd: str | None = Field(default=None, max_length=4096)
    timeout_s: int = Field(default=60, ge=1, le=600)


class GrepAction(_StrictModel):
    """ripgrep-style content search."""

    type: Literal["grep"]
    pattern: str = Field(min_length=1, max_length=2000)
    path: str = Field(default=".", max_length=4096)
    glob_pattern: str | None = Field(default=None, max_length=200)
    case_insensitive: bool = False
    context_lines: int = Field(default=0, ge=0, le=20)
    output_mode: Literal["content", "files_with_matches", "count"] = "content"
    max_results: int = Field(default=200, ge=1, le=20_000)


class FindFilesAction(_StrictModel):
    """Glob-style file search."""

    type: Literal["find_files"]
    pattern: str = Field(min_length=1, max_length=500)
    path: str = Field(default=".", max_length=4096)
    max_results: int = Field(default=500, ge=1, le=20_000)


Action = Union[  # noqa: UP007 — Pydantic v2 needs ``Union[...]`` for discriminated unions on some pythons
    ClickAction,
    MoveAction,
    TypeAction,
    HotkeyAction,
    ScrollAction,
    WaitAction,
    PowerShellAction,
    ExcelAction,
    ScreenshotAction,
    FileReadAction,
    FileWriteAction,
    FileEditAction,
    FileDeleteAction,
    ListDirAction,
    ApplyPatchAction,
    ShellAction,
    GrepAction,
    FindFilesAction,
]


class MemoryUpdate(_StrictModel):
    current_goal: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=512)


class AgentResponse(BaseModel):
    """Top-level Gemini response. Uses discriminated union on ``type``."""

    model_config = ConfigDict(extra="forbid")

    actions: list[Action] = Field(default_factory=list, max_length=25)
    memory_update: MemoryUpdate | None = None
